from __future__ import annotations

from pathlib import Path

from cryptography import x509

from cryptography.hazmat.primitives import serialization

from system import Settings, SettingsItem

from logger import Logger, LogLevel


class PaiCertStoreError(Exception):
    """
    Base exception for PAI certificate store failures.
    """


class PaiCertStoreConfigurationError(PaiCertStoreError):
    """
    Raised when required PAI file configuration is missing or invalid.
    """


class PaiCertStoreValidationError(PaiCertStoreError):
    """
    Raised when a PAI certificate file cannot be loaded or converted.
    """


class PaiCertStore:
    """
    Manage a single PAI certificate file.
    """

    def __init__(self) -> None:
        """
        Initialize the PAI certificate store and subscribe to settings.
        """
        self._pai: bytes | None = None

        Settings.subscribe(SettingsItem.PAI_FILE_PATH, self.on_path_changed)

        path = Settings.get(SettingsItem.PAI_FILE_PATH)
        self.on_path_changed(SettingsItem.PAI_FILE_PATH, path)

    def get(self) -> bytes:
        """
        Return cached PAI certificate bytes (DER format).
        """
        if self._pai is None:
            Logger.write(
                LogLevel.ALERT,
                'PAI store read failed: no PAI certificate is configured yet.',
            )
            raise PaiCertStoreConfigurationError(
                'The PAI certificate file has not been configured.'
            )

        return self._pai

    def on_path_changed(self, item: SettingsItem, value: object | None) -> None:
        """
        Apply PAI file changes from system.
        """
        if item != SettingsItem.PAI_FILE_PATH:
            return

        if value is None:
            self._pai = None
            return

        if not isinstance(value, Path):
            Logger.write(
                LogLevel.ALERT,
                'PAI path update failed: expected a Path value from settings.',
            )
            raise PaiCertStoreConfigurationError(
                'The PAI file path setting is invalid.'
            )

        self._load(value)

    def _load(self, path: Path) -> None:
        """
        Load and cache current PAI bytes (DER format).
        """
        try:
            pem_data = path.read_bytes()
        except OSError as exc:
            Logger.write(
                LogLevel.ALERT,
                'PAI file load failed: unable to read PAI certificate '
                f'from {path} ({type(exc).__name__}: {exc}).',
            )
            raise PaiCertStoreValidationError(
                'Failed to read the selected PAI certificate file.'
            ) from exc

        try:
            certificate = x509.load_pem_x509_certificate(pem_data)
            self._pai = certificate.public_bytes(serialization.Encoding.DER)
        except Exception as exc:
            Logger.write(
                LogLevel.ALERT,
                'PAI conversion failed: invalid PEM certificate format '
                f'at {path} ({type(exc).__name__}: {exc}).',
            )
            raise PaiCertStoreValidationError(
                'Failed to convert the selected PAI certificate PEM file.'
            ) from exc
