from __future__ import annotations

import json

import re

from enum import Enum

from pathlib import Path

from typing import Any, NamedTuple

from cryptography import x509

from cryptography.hazmat.primitives import serialization

from cryptography.hazmat.primitives.asymmetric import ec

from logger import Logger, LogLevel

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

    READY = 'ready'
    CONSUMED = 'consumed'
    ERROR = 'error'


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

    METADATA_FILENAME = 'stat.json'

    CERT_KEY_TOKEN_PATTERN = re.compile(
        r'(?<![A-Za-z0-9])(?P<kind>cert|key)(?![A-Za-z0-9])',
        re.IGNORECASE,
    )

    def __init__(self) -> None:
        """
        Initialize the DAC credential pool store and subscribe to settings.
        """
        self._directory: Path | None = None
        self._leased_material: DacMaterial | None = None

        Settings.subscribe(SettingsItem.DAC_POOL_DIR_PATH, self.on_path_changed)

        path = Settings.get(SettingsItem.DAC_POOL_DIR_PATH)
        self.on_path_changed(SettingsItem.DAC_POOL_DIR_PATH, path)

    def pull(self) -> DacMaterial:
        """
        Pull the next ready DAC credential pair.
        """
        if self._leased_material is not None:
            Logger.write(
                LogLevel.ALERT,
                'DAC pull blocked: a DAC credential pair is already in progress.',
            )
            raise DacCredentialPoolInProgressError(
                'A DAC credential pair is already in progress. '
                'Report it before pulling another one.'
            )

        self._require_directory()
        self._sync_metadata()

        metadata = self._load_metadata()
        entries = metadata.get('entries', {})
        if not isinstance(entries, dict):
            Logger.write(
                LogLevel.ALERT,
                'DAC pull failed: stat.json contains a non-object entries field.',
            )
            raise AttestationStoreError(
                'stat.json contains an invalid entries field.'
            )

        scanned = self._scan_directory()

        for base_name, item in sorted(entries.items()):
            if not isinstance(item, dict) or item.get('status') != DacStatus.READY:
                continue

            pair_info = scanned.get(base_name, {})
            cert_path = pair_info.get('cert')
            key_path = pair_info.get('key')

            if cert_path is None or key_path is None:
                self._mark_entry_as_error(metadata, item)
                continue

            try:
                material = self._load_dac_material(
                    base_name=base_name,
                    cert_path=cert_path,
                    key_path=key_path,
                )
            except Exception as exc:
                self._mark_entry_as_error(metadata, item)
                Logger.write(
                    LogLevel.ALERT,
                    'DAC pull skipped: failed to load certificate/key pair; '
                    'entry marked as ERROR. Verify file format and pairing. '
                    f'base={base_name} ({type(exc).__name__}: {exc})',
                )
                continue

            self._leased_material = material
            return material

        Logger.write(
            LogLevel.ALERT,
            'DAC pull failed: no READY certificate/key pair is available.',
        )
        raise DacCredentialPoolEmptyError(
            'No ready DAC certificate/key pair is '
            'available in the configured folder.'
        )

    def report(self, is_success: bool) -> None:
        """
        Report the result of the currently pulled DAC credential pair.
        """
        if self._leased_material is None:
            Logger.write(
                LogLevel.ALERT,
                'DAC report rejected: no in-progress DAC credential pair exists.',
            )
            raise DacCredentialPoolReportError(
                'There is no DAC credential pair in progress to report.'
            )

        metadata = self._load_metadata()
        entries = metadata.get('entries', {})
        if not isinstance(entries, dict):
            Logger.write(
                LogLevel.ALERT,
                'DAC report failed: metadata contains a non-object entries field.',
            )
            raise AttestationStoreError(
                'metadata.json contains an invalid entries field.'
            )

        base_name = self._leased_material.base_name
        item = entries.get(base_name)

        if not isinstance(item, dict):
            Logger.write(
                LogLevel.ALERT,
                'DAC report failed: pulled DAC entry is missing '
                'or invalid in stat.json. '
                f'base={base_name}',
            )
            raise AttestationStoreError(
                f"stat.json does not contain a valid DAC entry for '{base_name}'."
            )

        item['status'] = DacStatus.CONSUMED if is_success else DacStatus.ERROR
        self._save_metadata(metadata)
        self._leased_material = None

    def get_inventory_report(self) -> DacInventoryReport:
        """
        Return summary counts for total, ready, consumed, and error.
        """
        self._require_directory()
        self._sync_metadata()

        metadata = self._load_metadata()
        entries = metadata.get('entries', {})

        if not isinstance(entries, dict):
            Logger.write(
                LogLevel.ALERT,
                'DAC inventory report failed: metadata contains '
                'a non-object entries field.',
            )
            raise AttestationStoreError(
                'metadata.json contains an invalid entries field.'
            )

        total = len(entries)
        ready = 0
        consumed = 0
        error = 0

        for item in entries.values():
            status = item.get('status') if isinstance(item, dict) else None
            if status == DacStatus.READY:
                ready += 1
            elif status == DacStatus.CONSUMED:
                consumed += 1
            elif status == DacStatus.ERROR:
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

    def on_path_changed(self, item: SettingsItem, value: object | None) -> None:
        """
        Apply DAC pool directory changes from system.
        """
        if item != SettingsItem.DAC_POOL_DIR_PATH:
            return

        if value is None:
            self._directory = None
            self._leased_material = None
            return

        if not isinstance(value, Path):
            Logger.write(
                LogLevel.ALERT,
                'DAC directory update failed: expected a Path value from settings.',
            )
            raise AttestationStoreConfigurationError(
                'The DAC pool directory setting is invalid.'
            )

        self._load(value)

    def _load(self, path: Path) -> None:
        """
        Load DAC pool directory and synchronize metadata.
        """
        self._directory = path
        self._leased_material = None
        self._ensure_metadata_file()
        self._sync_metadata()

    def _mark_entry_as_error(
        self,
        metadata: dict[str, Any],
        entry: dict[str, Any],
    ) -> None:
        """
        Mark one metadata entry as ERROR and persist metadata.
        """
        entry['status'] = DacStatus.ERROR
        self._save_metadata(metadata)

    def _require_directory(self) -> Path:
        """
        Return the configured DAC directory.
        """
        if self._directory is None:
            Logger.write(
                LogLevel.ALERT,
                'DAC operation failed: DAC pool directory is not configured.',
            )
            raise AttestationStoreConfigurationError(
                'The DAC folder has not been configured.'
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
            'version': 1,
            'entries': {},
        }

    def _load_metadata(self) -> dict[str, Any]:
        """
        Load metadata.json.
        """
        self._ensure_metadata_file()
        metadata_path = self.get_metadata_path()

        try:
            with metadata_path.open('r', encoding='utf-8') as file:
                metadata = json.load(file)
        except OSError as exc:
            Logger.write(
                LogLevel.ALERT,
                'DAC metadata read failed: unable to read stat.json from DAC pool '
                f'directory ({type(exc).__name__}: {exc}).',
            )
            raise AttestationStoreError(
                'Failed to read metadata.json from the DAC folder.'
            ) from exc
        except json.JSONDecodeError as exc:
            Logger.write(
                LogLevel.ALERT,
                'DAC metadata parse failed: stat.json is not valid JSON '
                f'({type(exc).__name__}: {exc}).',
            )
            raise AttestationStoreError(
                'metadata.json is not a valid JSON file.'
            ) from exc

        if not isinstance(metadata, dict):
            Logger.write(
                LogLevel.ALERT,
                'DAC metadata format failed: stat.json root must be a JSON object.',
            )
            raise AttestationStoreError(
                'metadata.json must contain a JSON object.'
            )

        return metadata

    def _save_metadata(self, metadata: dict[str, Any]) -> None:
        """
        Save metadata.json.
        """
        metadata_path = self.get_metadata_path()

        try:
            with metadata_path.open('w', encoding='utf-8') as file:
                json.dump(metadata, file, indent=2, ensure_ascii=False)
                file.write('\n')
        except OSError as exc:
            Logger.write(
                LogLevel.ALERT,
                'DAC metadata write failed: unable to update stat.json in DAC pool '
                f'directory ({type(exc).__name__}: {exc}).',
            )
            raise AttestationStoreError(
                'Failed to write metadata.json in the DAC folder.'
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

        if path.suffix.lower() != '.pem':
            return None

        stem = path.stem
        matches = list(self.CERT_KEY_TOKEN_PATTERN.finditer(stem))

        if len(matches) != 1:
            return None

        match = matches[0]
        kind = match.group('kind').lower()

        normalized_stem = (
            stem[:match.start()] +
            '*' +
            stem[match.end():]
        )

        return f'{normalized_stem}.pem', kind

    def _scan_directory(self) -> dict[str, dict[str, Path]]:
        """
        Scan the DAC directory and group PEM files by normalized DAC pair name.
        """
        directory = self._require_directory()
        grouped: dict[str, dict[str, Path]] = {}

        for entry in directory.iterdir():
            if not entry.is_file():
                continue

            if entry.name == self.METADATA_FILENAME:
                continue

            normalized = self._normalize_pair_name(entry.name)
            if normalized is None:
                continue

            base_name, kind = normalized
            pair_info = grouped.setdefault(base_name, {})
            pair_info[kind] = entry.resolve()

        return grouped

    def _sync_metadata(self) -> None:
        """
        Synchronize metadata.json with the current DAC folder contents.
        """
        metadata = self._load_metadata()
        previous_entries = metadata.get('entries', {})
        if not isinstance(previous_entries, dict):
            previous_entries = {}

        scanned = self._scan_directory()
        merged_entries: dict[str, dict[str, DacStatus]] = {}

        for base_name, pair_info in scanned.items():
            cert_path = pair_info.get('cert')
            key_path = pair_info.get('key')

            previous = previous_entries.get(base_name, {})
            previous_status = (
                previous.get('status') if isinstance(previous, dict) else None
            )

            if cert_path is None or key_path is None:
                status = DacStatus.ERROR
            elif previous_status == DacStatus.CONSUMED:
                status = DacStatus.CONSUMED
            else:
                status = DacStatus.READY

            merged_entries[base_name] = {'status': status}

        metadata['entries'] = dict(sorted(merged_entries.items()))
        self._save_metadata(metadata)

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
            Logger.write(
                LogLevel.ALERT,
                'DAC certificate read failed: unable to read certificate file '
                f'{cert_path.name} ({type(exc).__name__}: {exc}).',
            )
            raise AttestationStoreError(
                f"Failed to read DAC certificate file '{cert_path.name}'."
            ) from exc

        try:
            key_pem = key_path.read_bytes()
        except OSError as exc:
            Logger.write(
                LogLevel.ALERT,
                'DAC private key read failed: unable to read private key file '
                f'{key_path.name} ({type(exc).__name__}: {exc}).',
            )
            raise AttestationStoreError(
                f"Failed to read DAC private key file '{key_path.name}'."
            ) from exc

        try:
            certificate = x509.load_pem_x509_certificate(cert_pem)
            dac_cert_der = certificate.public_bytes(serialization.Encoding.DER)
        except Exception as exc:
            Logger.write(
                LogLevel.ALERT,
                'DAC certificate conversion failed: invalid certificate PEM file '
                f'{cert_path.name} ({type(exc).__name__}: {exc}).',
            )
            raise AttestationStoreError(
                f"Failed to convert DAC certificate PEM file '{cert_path.name}'."
            ) from exc

        try:
            private_key = serialization.load_pem_private_key(
                key_pem,
                password=None,
            )
        except Exception as exc:
            Logger.write(
                LogLevel.ALERT,
                'DAC private key parse failed: invalid private key PEM file '
                f'{key_path.name} ({type(exc).__name__}: {exc}).',
            )
            raise AttestationStoreError(
                f"Failed to parse DAC private key PEM file '{key_path.name}'."
            ) from exc

        if not isinstance(private_key, ec.EllipticCurvePrivateKey):
            Logger.write(
                LogLevel.ALERT,
                'DAC private key type mismatch: expected EC private key format. '
                f'file={key_path.name}',
            )
            raise AttestationStoreError(
                f"The DAC private key '{key_path.name}' is not an EC private key."
            )

        private_numbers = private_key.private_numbers()
        public_numbers = private_key.public_key().public_numbers()

        dac_private_key = private_numbers.private_value.to_bytes(
            DAC_PRIVATE_KEY_SIZE,
            byteorder='big',
        )

        x = public_numbers.x.to_bytes(32, byteorder='big')
        y = public_numbers.y.to_bytes(32, byteorder='big')
        dac_public_key = b'\x04' + x + y

        if len(dac_public_key) != DAC_PUBLIC_KEY_SIZE:
            Logger.write(
                LogLevel.ALERT,
                'DAC public key length mismatch: derived key length is unexpected. '
                f'file={key_path.name}, length={len(dac_public_key)}',
            )
            raise AttestationStoreError(
                f"The DAC public key derived from '{key_path.name}' "
                f'has an unexpected length.'
            )

        return DacMaterial(
            base_name=base_name,
            dac_cert_der=dac_cert_der,
            dac_public_key=dac_public_key,
            dac_private_key=dac_private_key,
        )
