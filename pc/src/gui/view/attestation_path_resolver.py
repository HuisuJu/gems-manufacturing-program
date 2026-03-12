from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from system import Settings, SettingsItem


DacStatus = Literal["ready", "consumed", "error"]


class AttestationPathResolverError(Exception):
    """
    Base exception for attestation path resolver failures.
    """


class AttestationPathResolverConfigurationError(AttestationPathResolverError):
    """
    Raised when required configuration is missing.
    """


class DacCredentialPoolEmptyError(AttestationPathResolverError):
    """
    Raised when no ready DAC certificate/key pair is available.
    """


class DacCredentialPoolInProgressError(AttestationPathResolverError):
    """
    Raised when pull() is called while a previous DAC pair has not been
    reported yet.
    """


class DacCredentialPoolReportError(AttestationPathResolverError):
    """
    Raised when report() is called without an active pulled DAC pair.
    """


@dataclass(frozen=True, slots=True)
class DacCredentialPath:
    """
    One DAC certificate/private key path pair.
    """

    base_name: str
    cert_path: Path
    key_path: Path


@dataclass(frozen=True, slots=True)
class DacInventoryReport:
    """
    Summary report of DAC inventory state.
    """

    total: int
    ready: int
    consumed: int
    error: int


class DacCredentialPoolPathResolver:
    """
    Resolve DAC certificate/private key pairs from the configured DAC pool
    directory.

    The DAC pool directory path is driven by the global settings module.
    This resolver subscribes to DAC_POOL_DIR_PATH changes and updates its
    internal state automatically.
    """

    METADATA_FILENAME = "metadata.json"
    DAC_PAIR_PATTERN = re.compile(
        r"^(?P<base>.+)_(?P<kind>Cert|Key)\.pem$",
        re.IGNORECASE,
    )

    STATUS_READY: DacStatus = "ready"
    STATUS_CONSUMED: DacStatus = "consumed"
    STATUS_ERROR: DacStatus = "error"

    def __init__(self) -> None:
        """
        Initialize the DAC credential path resolver and subscribe to settings.
        """
        self._directory: Path | None = None
        self._leased_path: DacCredentialPath | None = None

        Settings.subscribe(
            SettingsItem.DAC_POOL_DIR_PATH,
            self._on_setting_changed,
        )

        current_value = Settings.get(SettingsItem.DAC_POOL_DIR_PATH)
        self._apply_directory(current_value)

    @property
    def directory(self) -> Path | None:
        """
        Return the configured DAC directory.
        """
        return self._directory

    def pull(self) -> DacCredentialPath:
        """
        Pull the next ready DAC certificate/key path pair.

        The pulled pair remains in progress until report() is called.

        Returns:
            The selected DAC certificate/key paths.

        Raises:
            DacCredentialPoolInProgressError: If a previous pull has not been
                reported yet.
            DacCredentialPoolEmptyError: If no ready DAC pair is available.
        """
        self._require_directory()

        if self._leased_path is not None:
            raise DacCredentialPoolInProgressError(
                "A DAC certificate/key pair is already in progress. Report it before pulling another one."
            )

        self._sync_metadata()

        metadata = self._load_metadata()
        entries = metadata.get("entries", {})
        if not isinstance(entries, dict):
            raise AttestationPathResolverError(
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

            path_pair = DacCredentialPath(
                base_name=base_name,
                cert_path=cert_path,
                key_path=key_path,
            )

            self._leased_path = path_pair
            return path_pair

        raise DacCredentialPoolEmptyError(
            "No ready DAC certificate/key pair is available in the configured folder."
        )

    def report(self, is_success: bool) -> None:
        """
        Report the result of the currently pulled DAC certificate/key pair.

        Args:
            is_success: True if provisioning succeeded, otherwise False.

        Raises:
            DacCredentialPoolReportError: If there is no active pulled DAC pair.
        """
        if self._leased_path is None:
            raise DacCredentialPoolReportError(
                "There is no DAC certificate/key pair in progress to report."
            )

        metadata = self._load_metadata()
        entries = metadata.get("entries", {})
        if not isinstance(entries, dict):
            raise AttestationPathResolverError(
                "metadata.json contains an invalid entries field."
            )

        base_name = self._leased_path.base_name
        item = entries.get(base_name)

        if not isinstance(item, dict):
            raise AttestationPathResolverError(
                f"metadata.json does not contain a valid DAC entry for '{base_name}'."
            )

        item["status"] = self.STATUS_CONSUMED if is_success else self.STATUS_ERROR
        self._save_metadata(metadata)
        self._leased_path = None

    def get_inventory_report(self) -> DacInventoryReport:
        """
        Return summary counts for total, ready, consumed, and error.
        """
        self._require_directory()
        self._sync_metadata()

        metadata = self._load_metadata()
        entries = metadata.get("entries", {})

        if not isinstance(entries, dict):
            raise AttestationPathResolverError(
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

    def _on_setting_changed(self, item: SettingsItem, value: object | None) -> None:
        """
        Apply DAC pool directory changes from system.
        """
        if item != SettingsItem.DAC_POOL_DIR_PATH:
            return

        self._apply_directory(value)

    def _apply_directory(self, value: object | None) -> None:
        """
        Apply the DAC directory value received from system.
        """
        if value is None:
            self._directory = None
            self._leased_path = None
            return

        if not isinstance(value, Path):
            raise AttestationPathResolverConfigurationError(
                "The DAC pool directory setting is invalid."
            )

        self._directory = value
        self._leased_path = None
        self._ensure_metadata_file()
        self._sync_metadata()

    def _require_directory(self) -> Path:
        """
        Return the configured DAC directory.

        Raises:
            AttestationPathResolverConfigurationError: If the directory is not set.
        """
        if self._directory is None:
            raise AttestationPathResolverConfigurationError(
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
            raise AttestationPathResolverError(
                "Failed to read metadata.json from the DAC folder."
            ) from exc
        except json.JSONDecodeError as exc:
            raise AttestationPathResolverError(
                "metadata.json is not a valid JSON file."
            ) from exc

        if not isinstance(metadata, dict):
            raise AttestationPathResolverError(
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
            raise AttestationPathResolverError(
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


class PaiCertPathResolver:
    """
    Resolve the configured PAI certificate file path from system.
    """

    def __init__(self) -> None:
        """
        Initialize the PAI certificate path resolver and subscribe to settings.
        """
        self._path: Path | None = None

        Settings.subscribe(
            SettingsItem.PAI_FILE_PATH,
            self._on_setting_changed,
        )

        current_value = Settings.get(SettingsItem.PAI_FILE_PATH)
        self._apply_path(current_value)

    def get_path(self) -> Path:
        """
        Return the configured PAI certificate file path.

        Raises:
            AttestationPathResolverConfigurationError: If the PAI file path is not set.
        """
        if self._path is None:
            raise AttestationPathResolverConfigurationError(
                "The PAI certificate file has not been configured."
            )

        return self._path

    def _on_setting_changed(self, item: SettingsItem, value: object | None) -> None:
        """
        Apply PAI file path changes from system.
        """
        if item != SettingsItem.PAI_FILE_PATH:
            return

        self._apply_path(value)

    def _apply_path(self, value: object | None) -> None:
        """
        Apply the PAI file path value received from system.
        """
        if value is None:
            self._path = None
            return

        if not isinstance(value, Path):
            raise AttestationPathResolverConfigurationError(
                "The PAI file path setting is invalid."
            )

        self._path = value


class CdPathResolver:
    """
    Resolve the configured Certification Declaration file path from system.
    """

    def __init__(self) -> None:
        """
        Initialize the CD file path resolver and subscribe to settings.
        """
        self._path: Path | None = None

        Settings.subscribe(
            SettingsItem.CD_FILE_PATH,
            self._on_setting_changed,
        )

        current_value = Settings.get(SettingsItem.CD_FILE_PATH)
        self._apply_path(current_value)

    def get_path(self) -> Path:
        """
        Return the configured Certification Declaration file path.

        Raises:
            AttestationPathResolverConfigurationError: If the CD file path is not set.
        """
        if self._path is None:
            raise AttestationPathResolverConfigurationError(
                "The Certification Declaration file has not been configured."
            )

        return self._path

    def _on_setting_changed(self, item: SettingsItem, value: object | None) -> None:
        """
        Apply CD file path changes from system.
        """
        if item != SettingsItem.CD_FILE_PATH:
            return

        self._apply_path(value)

    def _apply_path(self, value: object | None) -> None:
        """
        Apply the CD file path value received from system.
        """
        if value is None:
            self._path = None
            return

        if not isinstance(value, Path):
            raise AttestationPathResolverConfigurationError(
                "The Certification Declaration file path setting is invalid."
            )

        self._path = value