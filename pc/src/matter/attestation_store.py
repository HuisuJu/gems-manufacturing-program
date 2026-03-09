from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from cryptography import x509
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec


DacStatus = Literal["ready", "consumed", "error"]


class AttestationStoreError(Exception):
    """
    Base exception for attestation store failures.
    """


class AttestationStoreConfigurationError(AttestationStoreError):
    """
    Raised when required configuration is missing or invalid.
    """


class AttestationStoreValidationError(AttestationStoreError):
    """
    Raised when an attestation-related file fails validation.
    """


class DacCredentialPoolEmptyError(AttestationStoreError):
    """
    Raised when no ready DAC credential pair is available.
    """


class DacCredentialPoolInProgressError(AttestationStoreError):
    """
    Raised when pull() is called while a previous DAC pair has not been
    reported yet.
    """


class DacCredentialPoolReportError(AttestationStoreError):
    """
    Raised when report() is called without an active pulled DAC pair.
    """


@dataclass(frozen=True, slots=True)
class DacCredentialMaterial:
    """
    Converted DAC material for firmware provisioning.

    - dac_cert_der: DER-encoded DAC certificate
    - dac_public_key: uncompressed EC public key (65 bytes)
    - dac_private_key: raw EC private key scalar (32 bytes)
    """

    base_name: str
    dac_cert_der: bytes
    dac_public_key: bytes
    dac_private_key: bytes


@dataclass(frozen=True, slots=True)
class DacInventoryReport:
    """
    Summary report of DAC inventory state.
    """

    total: int
    ready: int
    consumed: int
    error: int


class DacCredentialPoolStore:
    """
    Manage a DAC credential folder and its metadata.json file.

    This class is responsible for:
    - scanning the DAC folder
    - maintaining metadata.json
    - resolving Cert/Key pairs by base name
    - providing pull()/report(is_success) semantics

    Status transitions:
    - ready -> consumed when report(True) is called
    - ready -> error when report(False) is called
    """

    METADATA_FILENAME = "metadata.json"
    DAC_PAIR_PATTERN = re.compile(
        r"^(?P<base>.+)_(?P<kind>Cert|Key)\.pem$",
        re.IGNORECASE,
    )

    STATUS_READY: DacStatus = "ready"
    STATUS_CONSUMED: DacStatus = "consumed"
    STATUS_ERROR: DacStatus = "error"

    DAC_PRIVATE_KEY_SIZE = 32
    DAC_PUBLIC_KEY_SIZE = 65

    def __init__(self) -> None:
        """
        Initialize an empty DAC credential pool store.
        """
        self._directory: Path | None = None
        self._leased_material: DacCredentialMaterial | None = None

    @property
    def directory(self) -> Path | None:
        """
        Return the configured DAC directory.
        """
        return self._directory

    def set_directory(self, directory: str | Path) -> None:
        """
        Configure the DAC credential directory.

        The metadata.json file is created if it does not exist, and existing
        metadata is synchronized with the folder contents.

        Args:
            directory: DAC credential folder path.

        Raises:
            AttestationStoreConfigurationError: If the path is invalid.
        """
        path = Path(directory).expanduser().resolve()

        if not path.exists():
            raise AttestationStoreConfigurationError(
                "The selected DAC folder does not exist."
            )

        if not path.is_dir():
            raise AttestationStoreConfigurationError(
                "The selected DAC path is not a folder."
            )

        self._directory = path
        self._leased_material = None
        self._ensure_metadata_file()
        self._sync_metadata()

    def pull(self) -> DacCredentialMaterial:
        """
        Pull the next ready DAC credential pair.

        The pulled pair remains in progress until report() is called.

        Returns:
            The converted DAC credential material.

        Raises:
            DacCredentialPoolInProgressError: If a previous pull has not been
                reported yet.
            DacCredentialPoolEmptyError: If no ready DAC pair is available.
        """
        self._require_directory()

        if self._leased_material is not None:
            raise DacCredentialPoolInProgressError(
                "A DAC credential pair is already in progress. Report it before pulling another one."
            )

        self._sync_metadata()

        metadata = self._load_metadata()
        entries = metadata.get("entries", {})
        if not isinstance(entries, dict):
            raise AttestationStoreError(
                "metadata.json contains an invalid entries field."
            )

        scanned = self._scan_directory()

        for base_name in sorted(entries.keys()):
            item = entries[base_name]
            if not isinstance(item, dict):
                continue

            if item.get("status") != self.STATUS_READY:
                continue

            pair_info = scanned.get(base_name, {})
            cert_path = pair_info.get("cert")
            key_path = pair_info.get("key")

            if cert_path is None or key_path is None:
                item["status"] = self.STATUS_ERROR
                self._save_metadata(metadata)
                continue

            try:
                material = self._load_dac_material(
                    base_name=base_name,
                    cert_path=cert_path,
                    key_path=key_path,
                )
            except Exception:
                item["status"] = self.STATUS_ERROR
                self._save_metadata(metadata)
                continue

            self._leased_material = material
            return material

        raise DacCredentialPoolEmptyError(
            "No ready DAC certificate/key pair is available in the configured folder."
        )

    def report(self, is_success: bool) -> None:
        """
        Report the result of the currently pulled DAC credential pair.

        Args:
            is_success: True if provisioning succeeded, otherwise False.

        Raises:
            DacCredentialPoolReportError: If there is no active pulled DAC pair.
        """
        if self._leased_material is None:
            raise DacCredentialPoolReportError(
                "There is no DAC credential pair in progress to report."
            )

        metadata = self._load_metadata()
        entries = metadata.get("entries", {})
        if not isinstance(entries, dict):
            raise AttestationStoreError(
                "metadata.json contains an invalid entries field."
            )

        base_name = self._leased_material.base_name
        item = entries.get(base_name)

        if not isinstance(item, dict):
            raise AttestationStoreError(
                f"metadata.json does not contain a valid DAC entry for '{base_name}'."
            )

        item["status"] = self.STATUS_CONSUMED if is_success else self.STATUS_ERROR
        self._save_metadata(metadata)
        self._leased_material = None

    def get_inventory_report(self) -> DacInventoryReport:
        """
        Return summary counts for total, ready, consumed, and error.
        """
        self._require_directory()
        self._sync_metadata()

        metadata = self._load_metadata()
        entries = metadata.get("entries", {})

        if not isinstance(entries, dict):
            raise AttestationStoreError(
                "metadata.json contains an invalid entries field."
            )

        total = len(entries)
        ready = 0
        consumed = 0
        error = 0

        for item in entries.values():
            if not isinstance(item, dict):
                continue

            status = item.get("status")
            if status == self.STATUS_READY:
                ready += 1
            elif status == self.STATUS_CONSUMED:
                consumed += 1
            elif status == self.STATUS_ERROR:
                error += 1

        return DacInventoryReport(
            total=total,
            ready=ready,
            consumed=consumed,
            error=error,
        )

    def get_metadata_path(self) -> Path:
        """
        Return the metadata.json path.
        """
        directory = self._require_directory()
        return directory / self.METADATA_FILENAME

    def _require_directory(self) -> Path:
        """
        Return the configured DAC directory.

        Raises:
            AttestationStoreConfigurationError: If the directory is not set.
        """
        if self._directory is None:
            raise AttestationStoreConfigurationError(
                "The DAC folder has not been configured."
            )

        return self._directory

    def _ensure_metadata_file(self) -> None:
        """
        Create metadata.json if it does not exist.
        """
        metadata_path = self.get_metadata_path()
        if metadata_path.exists():
            return

        self._save_metadata(self._default_metadata())

    def _default_metadata(self) -> dict[str, Any]:
        """
        Return the default metadata structure.
        """
        return {
            "version": 1,
            "entries": {},
        }

    def _load_metadata(self) -> dict[str, Any]:
        """
        Load metadata.json.
        """
        self._ensure_metadata_file()
        metadata_path = self.get_metadata_path()

        try:
            with metadata_path.open("r", encoding="utf-8") as file:
                metadata = json.load(file)
        except OSError as exc:
            raise AttestationStoreError(
                "Failed to read metadata.json from the DAC folder."
            ) from exc
        except json.JSONDecodeError as exc:
            raise AttestationStoreError(
                "metadata.json is not a valid JSON file."
            ) from exc

        if not isinstance(metadata, dict):
            raise AttestationStoreError(
                "metadata.json must contain a JSON object."
            )

        return metadata

    def _save_metadata(self, metadata: dict[str, Any]) -> None:
        """
        Save metadata.json.
        """
        metadata_path = self.get_metadata_path()

        try:
            with metadata_path.open("w", encoding="utf-8") as file:
                json.dump(metadata, file, indent=2, ensure_ascii=False)
                file.write("\n")
        except OSError as exc:
            raise AttestationStoreError(
                "Failed to write metadata.json in the DAC folder."
            ) from exc

    def _scan_directory(self) -> dict[str, dict[str, Path]]:
        """
        Scan the DAC directory and group PEM files by DAC base name.
        """
        directory = self._require_directory()
        grouped: dict[str, dict[str, Path]] = {}

        for entry in directory.iterdir():
            if not entry.is_file():
                continue

            if entry.name == self.METADATA_FILENAME:
                continue

            match = self.DAC_PAIR_PATTERN.match(entry.name)
            if match is None:
                continue

            base_name = match.group("base")
            kind = match.group("kind").lower()

            pair_info = grouped.setdefault(base_name, {})
            pair_info[kind] = entry.resolve()

        return grouped

    def _sync_metadata(self) -> None:
        """
        Synchronize metadata.json with the current DAC folder contents.

        Rules:
        - every detected DAC base name is represented in metadata.json
        - entries with both cert and key files become ready unless already
          consumed
        - entries missing cert or key become error
        - consumed entries remain consumed
        """
        metadata = self._load_metadata()
        previous_entries = metadata.get("entries", {})
        if not isinstance(previous_entries, dict):
            previous_entries = {}

        scanned = self._scan_directory()
        merged_entries: dict[str, dict[str, str]] = {}

        for base_name, pair_info in scanned.items():
            cert_path = pair_info.get("cert")
            key_path = pair_info.get("key")

            previous = previous_entries.get(base_name, {})
            previous_status = previous.get("status")

            if cert_path is None or key_path is None:
                status = self.STATUS_ERROR
            elif previous_status == self.STATUS_CONSUMED:
                status = self.STATUS_CONSUMED
            else:
                status = self.STATUS_READY

            merged_entries[base_name] = {"status": status}

        metadata["entries"] = dict(sorted(merged_entries.items()))
        self._save_metadata(metadata)

    def _load_dac_material(
        self,
        base_name: str,
        cert_path: Path,
        key_path: Path,
    ) -> DacCredentialMaterial:
        """
        Load and convert a DAC PEM cert/key pair.

        Output format:
        - DAC cert: DER bytes
        - DAC public key: uncompressed EC point (65 bytes)
        - DAC private key: raw scalar (32 bytes)
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
            self.DAC_PRIVATE_KEY_SIZE,
            byteorder="big",
        )

        x = public_numbers.x.to_bytes(32, byteorder="big")
        y = public_numbers.y.to_bytes(32, byteorder="big")
        dac_public_key = b"\x04" + x + y

        if len(dac_public_key) != self.DAC_PUBLIC_KEY_SIZE:
            raise AttestationStoreError(
                f"The DAC public key derived from '{key_path.name}' has an unexpected length."
            )

        return DacCredentialMaterial(
            base_name=base_name,
            dac_cert_der=dac_cert_der,
            dac_public_key=dac_public_key,
            dac_private_key=dac_private_key,
        )


class PaiCertStore:
    """
    Manage a single PAI certificate file.

    The configured PEM file is converted to DER bytes and cached in memory.
    """

    def __init__(self) -> None:
        """
        Initialize an empty PAI certificate store.
        """
        self._pai_cert_der: bytes | None = None

    def set_file(self, path: str | Path) -> None:
        """
        Load a PAI certificate PEM file and cache its DER bytes.

        Args:
            path: Path to the PAI certificate PEM file.

        Raises:
            AttestationStoreValidationError: If the file is invalid or cannot
                be converted.
        """
        file_path = Path(path).expanduser().resolve()

        if not file_path.exists():
            raise AttestationStoreValidationError(
                "The selected PAI certificate file does not exist."
            )

        if not file_path.is_file():
            raise AttestationStoreValidationError(
                "The selected PAI certificate path is not a file."
            )

        if file_path.suffix.lower() != ".pem":
            raise AttestationStoreValidationError(
                "The selected PAI certificate file must be a .pem file."
            )

        try:
            pem_data = file_path.read_bytes()
        except OSError as exc:
            raise AttestationStoreValidationError(
                "Failed to read the selected PAI certificate file."
            ) from exc

        try:
            certificate = x509.load_pem_x509_certificate(pem_data)
            self._pai_cert_der = certificate.public_bytes(serialization.Encoding.DER)
        except Exception as exc:
            raise AttestationStoreValidationError(
                "Failed to convert the selected PAI certificate PEM file."
            ) from exc

    def get_der(self) -> bytes:
        """
        Return the cached PAI certificate DER bytes.

        Raises:
            AttestationStoreConfigurationError: If the PAI certificate is not set.
        """
        if self._pai_cert_der is None:
            raise AttestationStoreConfigurationError(
                "The PAI certificate file has not been configured."
            )

        return self._pai_cert_der


class CdStore:
    """
    Manage a single Certification Declaration file.

    The configured DER file is read and cached in memory.
    """

    def __init__(self) -> None:
        """
        Initialize an empty CD store.
        """
        self._cd_der: bytes | None = None

    def set_file(self, path: str | Path) -> None:
        """
        Load a Certification Declaration DER file and cache its bytes.

        Args:
            path: Path to the CD DER file.

        Raises:
            AttestationStoreValidationError: If the file is invalid.
        """
        file_path = Path(path).expanduser().resolve()

        if not file_path.exists():
            raise AttestationStoreValidationError(
                "The selected Certification Declaration file does not exist."
            )

        if not file_path.is_file():
            raise AttestationStoreValidationError(
                "The selected Certification Declaration path is not a file."
            )

        if file_path.suffix.lower() != ".der":
            raise AttestationStoreValidationError(
                "The selected Certification Declaration file must be a .der file."
            )

        try:
            self._cd_der = file_path.read_bytes()
        except OSError as exc:
            raise AttestationStoreValidationError(
                "Failed to read the selected Certification Declaration file."
            ) from exc

    def get_der(self) -> bytes:
        """
        Return the cached Certification Declaration DER bytes.

        Raises:
            AttestationStoreConfigurationError: If the CD file is not set.
        """
        if self._cd_der is None:
            raise AttestationStoreConfigurationError(
                "The Certification Declaration file has not been configured."
            )

        return self._cd_der