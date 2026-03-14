from __future__ import annotations

from pathlib import Path

from system import Settings, SettingsItem


class CdCertStoreException(Exception):
    """Base exception for CD certificate store errors."""


class CdCertStore:
    """Store and provide one Certification Declaration file."""

    def __init__(self) -> None:
        """Initialize store and load configured CD path if available."""
        self.cd_cert: bytes | None = None

        configured_path = Settings.get(SettingsItem.CD_FILE_PATH)
        self.load(configured_path)

    def get(self) -> bytes | None:
        """Return loaded CD bytes."""
        return self.cd_cert

    def load(self, path: Path | None) -> None:
        """Load CD bytes from a `.def' file and save the path to settings."""
        if path is None:
            self.cd_cert = None
            Settings.clear(SettingsItem.CD_FILE_PATH)
        else:
            try:
                self.cd_cert = path.read_bytes()
            except Exception as e:
                self.cd_cert = None
                raise CdCertStoreException(f"Failed to load CD file: {e}") from e
            
            Settings.set(SettingsItem.CD_FILE_PATH, path)

cd_cert_store = CdCertStore()
