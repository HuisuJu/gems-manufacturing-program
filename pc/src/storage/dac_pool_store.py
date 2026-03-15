from __future__ import annotations

import json
import re
from enum import Enum
from pathlib import Path
from typing import Any, NamedTuple, Optional

from cryptography import x509
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

from system import Settings


class AttestationStoreError(Exception):
    """Base exception for attestation store failures."""


class AttestationStoreConfigurationError(AttestationStoreError):
    """Raised when the DAC pool configuration is invalid."""


class DacCredentialPoolEmptyError(AttestationStoreError):
    """Raised when no ready DAC credential pair is available."""


class DacCredentialPoolInProgressError(AttestationStoreError):
    """Raised when another DAC credential pair is already in progress."""


class DacCredentialPoolReportError(AttestationStoreError):
    """Raised when there is no in-progress DAC credential pair to update."""


DAC_PRIVATE_KEY_SIZE = 32
DAC_PUBLIC_KEY_SIZE = 65


class DacMaterial(NamedTuple):
    """Converted DAC material for firmware provisioning."""

    cert_der: bytes
    public_key: bytes
    private_key: bytes


class DacStatus(str, Enum):
    """DAC credential status values stored in metadata."""

    READY = "ready"
    PROGRESS = "progress"
    CONSUMED = "consumed"
    ERROR = "error"


class DacInventoryReport(NamedTuple):
    """Summary report of DAC inventory state."""

    total: int
    ready: int
    progress: int
    consumed: int
    error: int


class DacCredentialPoolStore:
    """Manage a DAC credential directory and its stat.json metadata."""

    DAC_POOL_DIR_SETTING_KEY = "dac_pool_dir"
    METADATA_FILENAME = "stat.json"
    _EXPECTED_FORMATS = [".pem"]

    CERT_KEY_TOKEN_PATTERN = re.compile(
        r"(?<![A-Za-z0-9])(?P<kind>cert|key)(?![A-Za-z0-9])",
        re.IGNORECASE,
    )

    _pool_path: Optional[Path]
    _metadata_path: Optional[Path]
    _entry: dict[str, DacStatus]

    def __init__(self) -> None:
        """Initialize the DAC pool store and load the configured directory if present."""
        self._pool_path = None
        self._metadata_path = None
        self._entry = {}

        configured_path = Settings.get(self.DAC_POOL_DIR_SETTING_KEY)

        if isinstance(configured_path, str) or configured_path is None:
            try:
                self.load(configured_path)
            except AttestationStoreError:
                self._pool_path = None
                self._metadata_path = None
                self._entry = {}
                Settings.clear(self.DAC_POOL_DIR_SETTING_KEY)
        else:
            Settings.clear(self.DAC_POOL_DIR_SETTING_KEY)

    @property
    def pool_path(self) -> Optional[str]:
        """Return the configured DAC pool directory path."""
        return str(self._pool_path) if self._pool_path else None

    @classmethod
    def expected_formats(cls) -> list[str]:
        """Return supported file extensions for UI usage."""
        return list(cls._EXPECTED_FORMATS)

    def load(self, path: Optional[str]) -> None:
        """
        Load a DAC pool directory and initialize in-memory state.

        The directory must contain at least one matching certificate/private-key
        pair. If `stat.json` does not exist, it is created automatically.
        """
        if path is None:
            self._pool_path = None
            self._metadata_path = None
            self._entry = {}
            Settings.clear(self.DAC_POOL_DIR_SETTING_KEY)
            return

        resolved_path = Path(path).expanduser().resolve()

        if not resolved_path.exists():
            raise AttestationStoreConfigurationError(
                "DAC pool setup failed: directory was not found. "
                f"path='{resolved_path}'"
            )

        if not resolved_path.is_dir():
            raise AttestationStoreConfigurationError(
                "DAC pool setup failed: configured path is not a directory. "
                f"path='{resolved_path}'"
            )

        metadata_path = resolved_path / self.METADATA_FILENAME
        if metadata_path.exists():
            metadata = self._load_metadata(metadata_path)
        else:
            metadata = self._create_metadata(metadata_path)

        entries = metadata.get("entries", {})
        if not isinstance(entries, dict):
            raise AttestationStoreError(
                "DAC pool metadata is invalid: 'entries' must be a JSON object. "
                f"path='{metadata_path}'"
            )

        self._pool_path = resolved_path
        self._metadata_path = metadata_path
        self._entry = {}

        scanned_base_names = self._scan(resolved_path)

        has_complete_pair = False
        for base_name in sorted(scanned_base_names):
            cert_path, key_path = self._resolve_path(base_name)

            if cert_path is not None and key_path is not None:
                has_complete_pair = True

            previous = entries.get(base_name, {})
            previous_status = (
                previous.get("status") if isinstance(previous, dict) else None
            )

            if cert_path is None or key_path is None:
                self._entry[base_name] = DacStatus.ERROR
            elif previous_status == DacStatus.CONSUMED:
                self._entry[base_name] = DacStatus.CONSUMED
            elif previous_status == DacStatus.ERROR:
                self._entry[base_name] = DacStatus.ERROR
            else:
                self._entry[base_name] = DacStatus.READY

        if not has_complete_pair:
            self._pool_path = None
            self._metadata_path = None
            self._entry = {}
            raise AttestationStoreConfigurationError(
                "DAC pool setup failed: no complete PEM certificate/private-key "
                f"pair was found. path='{resolved_path}'"
            )

        self._save_metadata(metadata_path, self._entry)
        Settings.set(self.DAC_POOL_DIR_SETTING_KEY, str(resolved_path))

    def get_material(self) -> tuple[str, DacMaterial]:
        """Return the next ready DAC credential pair and mark it as in progress."""
        if self._pool_path is None or self._metadata_path is None:
            raise AttestationStoreConfigurationError(
                "DAC pool operation failed: pool directory is not configured."
            )

        if any(status == DacStatus.PROGRESS for status in self._entry.values()):
            raise DacCredentialPoolInProgressError(
                "DAC material request blocked: another credential pair is already "
                "marked as in progress. Finalize that pair before requesting a new one."
            )

        for base_name in sorted(self._entry):
            if self._entry[base_name] != DacStatus.READY:
                continue

            cert_path, key_path = self._resolve_path(base_name)

            if cert_path is None or key_path is None:
                self._save_metadata(self._metadata_path, self._entry)
                continue

            try:
                material = self._load_dac_material(
                    cert_path=cert_path,
                    key_path=key_path,
                )
            except Exception:
                self._entry[base_name] = DacStatus.ERROR
                self._save_metadata(self._metadata_path, self._entry)
                continue

            self._entry[base_name] = DacStatus.PROGRESS
            self._save_metadata(self._metadata_path, self._entry)
            return base_name, material

        raise DacCredentialPoolEmptyError(
            "DAC material request failed: no ready certificate/private-key pair is "
            "available in the configured pool."
        )

    def set_material_state(self, base_name: str, is_success: bool) -> None:
        """
        Finalize the state of an in-progress DAC credential pair.

        `True` marks it as consumed.
        `False` marks it as error.
        """
        if self._pool_path is None or self._metadata_path is None:
            raise AttestationStoreConfigurationError(
                "DAC pool operation failed: pool directory is not configured."
            )

        current_status = self._entry.get(base_name)
        if current_status is None:
            raise DacCredentialPoolReportError(
                "DAC material state update failed: requested entry was not found. "
                f"base_name='{base_name}'"
            )

        if current_status != DacStatus.PROGRESS:
            raise DacCredentialPoolReportError(
                "DAC material state update failed: entry is not marked as in progress. "
                f"base_name='{base_name}', current_status='{current_status}'"
            )

        self._entry[base_name] = DacStatus.CONSUMED if is_success else DacStatus.ERROR
        self._save_metadata(self._metadata_path, self._entry)

    def get_inventory_report(self) -> DacInventoryReport:
        """Return summary counts for total, ready, progress, consumed, and error."""
        if self._pool_path is None or self._metadata_path is None:
            raise AttestationStoreConfigurationError(
                "DAC pool operation failed: pool directory is not configured."
            )

        total = len(self._entry)
        ready = 0
        progress = 0
        consumed = 0
        error = 0

        for status in self._entry.values():
            if status == DacStatus.READY:
                ready += 1
            elif status == DacStatus.PROGRESS:
                progress += 1
            elif status == DacStatus.CONSUMED:
                consumed += 1
            elif status == DacStatus.ERROR:
                error += 1

        return DacInventoryReport(
            total=total,
            ready=ready,
            progress=progress,
            consumed=consumed,
            error=error,
        )

    def _load_metadata(self, metadata_path: Path) -> dict[str, Any]:
        """Load metadata from stat.json."""
        if not metadata_path.is_file():
            raise AttestationStoreConfigurationError(
                "DAC pool metadata load failed: metadata path is not a file. "
                f"path='{metadata_path}'"
            )

        try:
            with metadata_path.open("r", encoding="utf-8") as file:
                metadata = json.load(file)
        except OSError as exc:
            raise AttestationStoreError(
                "DAC pool metadata load failed: could not read stat.json. "
                f"path='{metadata_path}', reason='{type(exc).__name__}: {exc}'"
            ) from exc
        except json.JSONDecodeError as exc:
            raise AttestationStoreError(
                "DAC pool metadata load failed: stat.json is not valid JSON. "
                f"path='{metadata_path}', reason='{type(exc).__name__}: {exc}'"
            ) from exc

        if not isinstance(metadata, dict):
            raise AttestationStoreError(
                "DAC pool metadata is invalid: root value must be a JSON object. "
                f"path='{metadata_path}'"
            )

        return metadata

    def _create_metadata(self, metadata_path: Path) -> dict[str, Any]:
        """Create a default stat.json file and return its content."""
        metadata = {
            "version": 1,
            "entries": {},
        }

        try:
            with metadata_path.open("w", encoding="utf-8") as file:
                json.dump(metadata, file, indent=2, ensure_ascii=False)
                file.write("\n")
        except OSError as exc:
            raise AttestationStoreError(
                "DAC pool metadata creation failed: could not write stat.json. "
                f"path='{metadata_path}', reason='{type(exc).__name__}: {exc}'"
            ) from exc

        return metadata

    def _save_metadata(
        self,
        metadata_path: Path,
        entry: dict[str, DacStatus],
    ) -> None:
        """Persist entry states to stat.json."""
        metadata = {
            "version": 1,
            "entries": {
                base_name: {"status": status}
                for base_name, status in sorted(entry.items())
            },
        }

        try:
            with metadata_path.open("w", encoding="utf-8") as file:
                json.dump(metadata, file, indent=2, ensure_ascii=False)
                file.write("\n")
        except OSError as exc:
            raise AttestationStoreError(
                "DAC pool metadata save failed: could not write stat.json. "
                f"path='{metadata_path}', reason='{type(exc).__name__}: {exc}'"
            ) from exc

    def _normalize_path(self, filename: str) -> Optional[str]:
        """
        Return a normalized base name from a PEM filename.

        Examples:
            aeg_key_g23535.pem  -> aeg_*_g23535.pem
            aeg_key.pem         -> aeg_*.pem
            key_g23535.pem      -> *_g23535.pem
            cert.pem            -> *.pem
        """
        path = Path(filename)
        if path.suffix.lower() != ".pem":
            return None

        stem = path.stem
        matches = list(self.CERT_KEY_TOKEN_PATTERN.finditer(stem))
        if len(matches) != 1:
            return None

        match = matches[0]
        prefix = stem[: match.start()]
        suffix = stem[match.end() :]

        if prefix.endswith("_"):
            prefix = prefix[:-1]

        if suffix.startswith("_"):
            suffix = suffix[1:]

        parts: list[str] = []
        if prefix:
            parts.append(prefix)
        parts.append("*")
        if suffix:
            parts.append(suffix)

        normalized_stem = "_".join(parts)
        return f"{normalized_stem}.pem"

    def _resolve_path(
        self,
        base_name: str,
    ) -> tuple[Optional[Path], Optional[Path]]:
        """Resolve certificate and key file paths for one base name."""
        if self._pool_path is None:
            raise AttestationStoreConfigurationError(
                "DAC path resolution failed: pool directory is not configured."
            )

        cert_path: Optional[Path] = None
        key_path: Optional[Path] = None

        for entry in self._pool_path.iterdir():
            if not entry.is_file() or entry.name == self.METADATA_FILENAME:
                continue

            normalized_base_name = self._normalize_path(entry.name)
            if normalized_base_name != base_name:
                continue

            stem_lower = entry.stem.lower()
            if "cert" in stem_lower:
                cert_path = entry.resolve()
            elif "key" in stem_lower:
                key_path = entry.resolve()

        if cert_path is None or key_path is None:
            self._entry.pop(base_name, None)

        return cert_path, key_path

    def _scan(self, directory: Path) -> set[str]:
        """Scan the DAC directory and collect normalized base names."""
        base_names: set[str] = set()

        for entry in directory.iterdir():
            if not entry.is_file() or entry.name == self.METADATA_FILENAME:
                continue

            base_name = self._normalize_path(entry.name)
            if base_name is not None:
                base_names.add(base_name)

        return base_names

    def _load_dac_material(
        self,
        cert_path: Path,
        key_path: Path,
    ) -> DacMaterial:
        """Load and convert a DAC PEM certificate/private-key pair."""
        try:
            cert_pem = cert_path.read_bytes()
        except OSError as exc:
            raise AttestationStoreError(
                "DAC material load failed: could not read certificate file. "
                f"path='{cert_path}', reason='{type(exc).__name__}: {exc}'"
            ) from exc

        try:
            key_pem = key_path.read_bytes()
        except OSError as exc:
            raise AttestationStoreError(
                "DAC material load failed: could not read private key file. "
                f"path='{key_path}', reason='{type(exc).__name__}: {exc}'"
            ) from exc

        try:
            certificate = x509.load_pem_x509_certificate(cert_pem)
            cert_der = certificate.public_bytes(serialization.Encoding.DER)
        except Exception as exc:
            raise AttestationStoreError(
                "DAC material load failed: could not parse certificate PEM or "
                f"convert it to DER. path='{cert_path}', "
                f"reason='{type(exc).__name__}: {exc}'"
            ) from exc

        try:
            private_key = serialization.load_pem_private_key(
                key_pem,
                password=None,
            )
        except Exception as exc:
            raise AttestationStoreError(
                "DAC material load failed: could not parse private key PEM. "
                f"path='{key_path}', reason='{type(exc).__name__}: {exc}'"
            ) from exc

        if not isinstance(private_key, ec.EllipticCurvePrivateKey):
            raise AttestationStoreError(
                "DAC material load failed: private key is not an EC key. "
                f"path='{key_path}', actual_type='{type(private_key).__name__}'"
            )

        private_numbers = private_key.private_numbers()
        public_numbers = private_key.public_key().public_numbers()

        private_key_bytes = private_numbers.private_value.to_bytes(
            DAC_PRIVATE_KEY_SIZE,
            byteorder="big",
        )

        x = public_numbers.x.to_bytes(32, byteorder="big")
        y = public_numbers.y.to_bytes(32, byteorder="big")
        public_key = b"\x04" + x + y

        if len(private_key_bytes) != DAC_PRIVATE_KEY_SIZE:
            raise AttestationStoreError(
                "DAC material load failed: derived private key length is invalid. "
                f"path='{key_path}', expected={DAC_PRIVATE_KEY_SIZE}, "
                f"actual={len(private_key_bytes)}"
            )

        if len(public_key) != DAC_PUBLIC_KEY_SIZE:
            raise AttestationStoreError(
                "DAC material load failed: derived public key length is invalid. "
                f"path='{key_path}', expected={DAC_PUBLIC_KEY_SIZE}, "
                f"actual={len(public_key)}"
            )

        return DacMaterial(
            cert_der=cert_der,
            public_key=public_key,
            private_key=private_key_bytes,
        )


dac_pool_store = DacCredentialPoolStore()
