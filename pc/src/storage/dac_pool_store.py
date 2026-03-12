from __future__ import annotations

import json
import re
from enum import Enum
from pathlib import Path
from typing import Any, NamedTuple

from cryptography import x509
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

from system import Settings, SettingsItem


class AttestationStoreError(Exception):
    """
    Base exception for attestation store failures.
    """


class AttestationStoreConfigurationError(AttestationStoreError):
    """
    Raised when required configuration is missing.
    """


class DacCredentialPoolEmptyError(AttestationStoreError):
    """
    Raised when no ready DAC credential pair is available.
    """


class DacCredentialPoolInProgressError(AttestationStoreError):
    """
    Raised when pull() is called while a previous DAC pair is in progress.
    """


class DacCredentialPoolReportError(AttestationStoreError):
    """
    Raised when report() is called without an active pulled DAC pair.
    """


DAC_PRIVATE_KEY_SIZE = 32
DAC_PUBLIC_KEY_SIZE = 65


class DacMaterial(NamedTuple):
    """
    Converted DAC material for firmware provisioning.
    """

    base_name: str
    dac_cert_der: bytes
    dac_public_key: bytes
    dac_private_key: bytes


class DacStatus(str, Enum):
    """
    DAC credential status values stored in metadata.
    """

    READY = "ready"
    CONSUMED = "consumed"
    ERROR = "error"


class DacInventoryReport(NamedTuple):
    """
    Summary report of DAC inventory state.
    """

    total: int
    ready: int
    consumed: int
    error: int


class DacCredentialPoolStore:
    """
    Manage a DAC credential folder and its stat.json file.
    """

    METADATA_FILENAME = "stat.json"

    CERT_KEY_TOKEN_PATTERN = re.compile(
        r"(?<![A-Za-z0-9])(?P<kind>cert|key)(?![A-Za-z0-9])",
        re.IGNORECASE,
    )

    def __init__(self) -> None:
        """
        Initialize the DAC credential pool store and subscribe to settings.
        """
        self._directory: Path | None = None
        self._metadata_path: Path | None = None
        self._metadata: dict[str, Any] | None = None
        self._statistics = DacInventoryReport(
            total=0,
            ready=0,
            consumed=0,
            error=0,
        )
        self._leased_material: DacMaterial | None = None

        Settings.subscribe(SettingsItem.DAC_POOL_DIR_PATH, self.on_path_changed)

        configured_path = Settings.get(SettingsItem.DAC_POOL_DIR_PATH)
        self.load(configured_path)

    def load(self, path: Path | None) -> None:
        """
        Load the DAC pool directory and stat.json, then synchronize metadata.
        """
        self._leased_material = None

        if path is None:
            self._directory = None
            self._metadata_path = None
            self._metadata = None
            self._statistics = DacInventoryReport(
                total=0,
                ready=0,
                consumed=0,
                error=0,
            )
            return

        if not isinstance(path, Path):
            raise AttestationStoreConfigurationError(
                "The DAC pool directory setting is invalid."
            )

        if not path.exists():
            raise AttestationStoreConfigurationError(
                f"The DAC folder does not exist: '{path}'."
            )

        if not path.is_dir():
            raise AttestationStoreConfigurationError(
                f"The DAC path is not a directory: '{path}'."
            )

        metadata_path = path / self.METADATA_FILENAME
        if not metadata_path.exists():
            raise AttestationStoreConfigurationError(
                f"Required metadata file '{self.METADATA_FILENAME}' "
                f"is missing in '{path}'."
            )

        if not metadata_path.is_file():
            raise AttestationStoreConfigurationError(
                f"Metadata path is not a file: '{metadata_path}'."
            )

        scanned = self._scan_directory(path)
        has_complete_pair = any(
            pair_info.get("cert") is not None and pair_info.get("key") is not None
            for pair_info in scanned.values()
        )
        if not has_complete_pair:
            raise AttestationStoreConfigurationError(
                "The DAC folder must contain at least one valid PEM cert/key pair."
            )

        try:
            with metadata_path.open("r", encoding="utf-8") as file:
                metadata = json.load(file)
        except OSError as exc:
            raise AttestationStoreError(
                "Failed to read stat.json from the DAC folder."
            ) from exc
        except json.JSONDecodeError as exc:
            raise AttestationStoreError(
                "stat.json is not a valid JSON file."
            ) from exc

        if not isinstance(metadata, dict):
            raise AttestationStoreError(
                "stat.json must contain a JSON object."
            )

        previous_entries = metadata.get("entries", {})
        if not isinstance(previous_entries, dict):
            raise AttestationStoreError(
                "stat.json contains an invalid entries field."
            )

        merged_entries: dict[str, dict[str, DacStatus]] = {}

        for base_name, pair_info in scanned.items():
            cert_path = pair_info.get("cert")
            key_path = pair_info.get("key")

            previous = previous_entries.get(base_name, {})
            previous_status = (
                previous.get("status") if isinstance(previous, dict) else None
            )

            if cert_path is None or key_path is None:
                status = DacStatus.ERROR
            elif previous_status == DacStatus.CONSUMED:
                status = DacStatus.CONSUMED
            else:
                status = DacStatus.READY

            merged_entries[base_name] = {"status": status}

        metadata["version"] = metadata.get("version", 1)
        metadata["entries"] = dict(sorted(merged_entries.items()))

        try:
            with metadata_path.open("w", encoding="utf-8") as file:
                json.dump(metadata, file, indent=2, ensure_ascii=False)
                file.write("\n")
        except OSError as exc:
            raise AttestationStoreError(
                "Failed to write stat.json in the DAC folder."
            ) from exc

        total = len(metadata["entries"])
        ready = 0
        consumed = 0
        error = 0

        for item in metadata["entries"].values():
            status = item.get("status") if isinstance(item, dict) else None
            if status == DacStatus.READY:
                ready += 1
            elif status == DacStatus.CONSUMED:
                consumed += 1
            elif status == DacStatus.ERROR:
                error += 1

        self._directory = path
        self._metadata_path = metadata_path
        self._metadata = metadata
        self._statistics = DacInventoryReport(
            total=total,
            ready=ready,
            consumed=consumed,
            error=error,
        )

    def pull(self) -> DacMaterial:
        """
        Pull the next ready DAC credential pair.
        """
        if self._directory is None or self._metadata_path is None or self._metadata is None:
            raise AttestationStoreConfigurationError(
                "The DAC folder has not been configured."
            )

        if self._leased_material is not None:
            raise DacCredentialPoolInProgressError(
                "A DAC credential pair is already in progress. "
                "Report it before pulling another one."
            )

        entries = self._metadata.get("entries", {})
        if not isinstance(entries, dict):
            raise AttestationStoreError(
                "stat.json contains an invalid entries field."
            )

        scanned = self._scan_directory(self._directory)

        for base_name, item in sorted(entries.items()):
            if not isinstance(item, dict) or item.get("status") != DacStatus.READY:
                continue

            pair_info = scanned.get(base_name, {})
            cert_path = pair_info.get("cert")
            key_path = pair_info.get("key")

            if cert_path is None or key_path is None:
                item["status"] = DacStatus.ERROR
                self._save_current_metadata()

                self._statistics = DacInventoryReport(
                    total=self._statistics.total,
                    ready=max(0, self._statistics.ready - 1),
                    consumed=self._statistics.consumed,
                    error=self._statistics.error + 1,
                )
                continue

            try:
                material = self._load_dac_material(
                    base_name=base_name,
                    cert_path=cert_path,
                    key_path=key_path,
                )
            except Exception:
                item["status"] = DacStatus.ERROR
                self._save_current_metadata()

                self._statistics = DacInventoryReport(
                    total=self._statistics.total,
                    ready=max(0, self._statistics.ready - 1),
                    consumed=self._statistics.consumed,
                    error=self._statistics.error + 1,
                )
                continue

            self._leased_material = material
            return material

        raise DacCredentialPoolEmptyError(
            "No ready DAC certificate/key pair is "
            "available in the configured folder."
        )

    def report(self, is_success: bool) -> None:
        """
        Report the result of the currently pulled DAC credential pair.
        """
        if self._directory is None or self._metadata_path is None or self._metadata is None:
            raise AttestationStoreConfigurationError(
                "The DAC folder has not been configured."
            )

        if self._leased_material is None:
            raise DacCredentialPoolReportError(
                "There is no DAC credential pair in progress to report."
            )

        entries = self._metadata.get("entries", {})
        if not isinstance(entries, dict):
            raise AttestationStoreError(
                "stat.json contains an invalid entries field."
            )

        base_name = self._leased_material.base_name
        item = entries.get(base_name)

        if not isinstance(item, dict):
            raise AttestationStoreError(
                f"stat.json does not contain a valid DAC entry for '{base_name}'."
            )

        previous_status = item.get("status")
        new_status = DacStatus.CONSUMED if is_success else DacStatus.ERROR
        item["status"] = new_status

        self._save_current_metadata()

        ready = self._statistics.ready
        consumed = self._statistics.consumed
        error = self._statistics.error

        if previous_status == DacStatus.READY:
            ready = max(0, ready - 1)
            if new_status == DacStatus.CONSUMED:
                consumed += 1
            else:
                error += 1
        elif previous_status == DacStatus.CONSUMED and new_status == DacStatus.ERROR:
            consumed = max(0, consumed - 1)
            error += 1
        elif previous_status == DacStatus.ERROR and new_status == DacStatus.CONSUMED:
            error = max(0, error - 1)
            consumed += 1

        self._statistics = DacInventoryReport(
            total=self._statistics.total,
            ready=ready,
            consumed=consumed,
            error=error,
        )

        self._leased_material = None

    def get_inventory_report(self) -> DacInventoryReport:
        """
        Return summary counts for total, ready, consumed, and error.
        """
        if self._directory is None or self._metadata_path is None or self._metadata is None:
            raise AttestationStoreConfigurationError(
                "The DAC folder has not been configured."
            )

        return self._statistics

    def on_path_changed(self, item: SettingsItem, value: object | None) -> None:
        """
        Apply DAC pool directory changes from settings.
        """
        if item != SettingsItem.DAC_POOL_DIR_PATH:
            return

        if value is not None and not isinstance(value, Path):
            raise AttestationStoreConfigurationError(
                "The DAC pool directory setting is invalid."
            )

        self.load(value)

    def _save_current_metadata(self) -> None:
        """
        Persist the currently loaded metadata to stat.json.
        """
        if self._metadata_path is None or self._metadata is None:
            raise AttestationStoreConfigurationError(
                "The DAC folder has not been configured."
            )

        try:
            with self._metadata_path.open("w", encoding="utf-8") as file:
                json.dump(self._metadata, file, indent=2, ensure_ascii=False)
                file.write("\n")
        except OSError as exc:
            raise AttestationStoreError(
                "Failed to write stat.json in the DAC folder."
            ) from exc

    def _normalize_pair_name(self, filename: str) -> tuple[str, str] | None:
        """
        Return normalized pair key and kind from a PEM filename.

        Supported examples:
            xx_Cert.pem    -> ("xx_*.pem", "cert")
            xx_Key.pem     -> ("xx_*.pem", "key")
            Cert_xx.pem    -> ("*_xx.pem", "cert")
            Key_xx.pem     -> ("*_xx.pem", "key")
            xx_cert_yy.pem -> ("xx_*_yy.pem", "cert")
            xx_key_yy.pem  -> ("xx_*_yy.pem", "key")
        """
        path = Path(filename)
        if path.suffix.lower() != ".pem":
            return None

        stem = path.stem
        matches = list(self.CERT_KEY_TOKEN_PATTERN.finditer(stem))
        if len(matches) != 1:
            return None

        match = matches[0]
        kind = match.group("kind").lower()
        normalized_stem = stem[:match.start()] + "*" + stem[match.end():]

        return f"{normalized_stem}.pem", kind

    def _scan_directory(self, directory: Path) -> dict[str, dict[str, Path]]:
        """
        Scan the DAC directory and group PEM files by normalized DAC pair name.
        """
        grouped: dict[str, dict[str, Path]] = {}

        for entry in directory.iterdir():
            if not entry.is_file() or entry.name == self.METADATA_FILENAME:
                continue

            normalized = self._normalize_pair_name(entry.name)
            if normalized is None:
                continue

            base_name, kind = normalized
            grouped.setdefault(base_name, {})[kind] = entry.resolve()

        return grouped

    def _load_dac_material(
        self,
        base_name: str,
        cert_path: Path,
        key_path: Path,
    ) -> DacMaterial:
        """
        Load and convert a DAC PEM cert/key pair.
        """
        try:
            cert_pem = cert_path.read_bytes()
        except OSError as exc:
            raise AttestationStoreError(
                f"Failed to read DAC certificate file '{cert_path.name}'."
            ) from exc

        try:
            key_pem = key_path.read_bytes()
        except OSError as exc:
            raise AttestationStoreError(
                f"Failed to read DAC private key file '{key_path.name}'."
            ) from exc

        try:
            certificate = x509.load_pem_x509_certificate(cert_pem)
            dac_cert_der = certificate.public_bytes(serialization.Encoding.DER)
        except Exception as exc:
            raise AttestationStoreError(
                f"Failed to convert DAC certificate PEM file '{cert_path.name}'."
            ) from exc

        try:
            private_key = serialization.load_pem_private_key(
                key_pem,
                password=None,
            )
        except Exception as exc:
            raise AttestationStoreError(
                f"Failed to parse DAC private key PEM file '{key_path.name}'."
            ) from exc

        if not isinstance(private_key, ec.EllipticCurvePrivateKey):
            raise AttestationStoreError(
                f"The DAC private key '{key_path.name}' is not an EC private key."
            )

        private_numbers = private_key.private_numbers()
        public_numbers = private_key.public_key().public_numbers()

        dac_private_key = private_numbers.private_value.to_bytes(
            DAC_PRIVATE_KEY_SIZE,
            byteorder="big",
        )

        x = public_numbers.x.to_bytes(32, byteorder="big")
        y = public_numbers.y.to_bytes(32, byteorder="big")
        dac_public_key = b"\x04" + x + y

        if len(dac_public_key) != DAC_PUBLIC_KEY_SIZE:
            raise AttestationStoreError(
                f"The DAC public key derived from '{key_path.name}' "
                f"has an unexpected length."
            )

        return DacMaterial(
            base_name=base_name,
            dac_cert_der=dac_cert_der,
            dac_public_key=dac_public_key,
            dac_private_key=dac_private_key,
        )
    
dac_pool_store = DacCredentialPoolStore()
