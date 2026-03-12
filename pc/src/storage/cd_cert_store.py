from __future__ import annotations

from pathlib import Path

from system import Settings, SettingsItem

from logger import Logger, LogLevel


class CdCertStoreError(Exception):
    """
    Base exception for CD certificate store failures.
    """


class CdCertStoreConfigurationError(CdCertStoreError):
    """
    Raised when required CD file configuration is missing or invalid.
    """


class CdCertStoreValidationError(CdCertStoreError):
    """
    Raised when a CD file cannot be loaded.
    """


class CdStore:
    """
    Manage a single Certification Declaration file.
    """

    def __init__(self) -> None:
        """
        Initialize the CD store and subscribe to settings.
        """
        self._cd: bytes | None = None

        Settings.subscribe(SettingsItem.CD_FILE_PATH, self.on_path_changed)

        path = Settings.get(SettingsItem.CD_FILE_PATH)
        self.on_path_changed(SettingsItem.CD_FILE_PATH, path)

    def get(self) -> bytes:
        """
        Return cached Certification Declaration bytes (DER format).
        """
        if self._cd is None:
            Logger.write(
                LogLevel.ALERT,
                'CD store read failed: '
                'no Certification Declaration is configured yet.',
            )
            raise CdCertStoreConfigurationError(
                'The Certification Declaration file has not been configured.'
            )

        return self._cd

    def on_path_changed(self, item: SettingsItem, value: object | None) -> None:
        """
        Apply CD file changes from system.
        """
        if item != SettingsItem.CD_FILE_PATH:
            return

        if value is None:
            self._cd = None
            return

        if not isinstance(value, Path):
            Logger.write(
                LogLevel.ALERT,
                'CD path update failed: expected a Path value from settings.',
            )
            raise CdCertStoreConfigurationError(
                'The Certification Declaration file path setting is invalid.'
            )

        self._load(value)

    def _load(self, path: Path) -> None:
        """
        Load and cache current CD bytes (DER format).
        """
        try:
            self._cd = path.read_bytes()
        except OSError as exc:
            Logger.write(
                LogLevel.ALERT,
                'CD file load failed: unable to read Certification Declaration '
                f'from {path} ({type(exc).__name__}: {exc}).',
            )
            raise CdCertStoreValidationError(
                'Failed to read the selected Certification Declaration file.'
            ) from exc
