from __future__ import annotations

from pathlib import Path
from typing import Optional

from system import Settings


class CdCertStoreException(Exception):
    """Base exception for CD certificate store errors."""


class CdCertStoreLoadError(CdCertStoreException):
    """Raised when loading the CD certificate fails."""


class CdCertStore:
    """Store and provide one Certification Declaration certificate."""

    CD_CERT_PATH_KEY = "cd_cert_path"
    _EXPECTED_FORMATS = [".der"]

    _cd_cert: Optional[bytes]
    _cd_cert_path: Optional[Path]

    def __init__(self) -> None:
        """Initialize the store and load configured CD if present."""
        self._cd_cert = None
        self._cd_cert_path = None

        configured_path = Settings.get(self.CD_CERT_PATH_KEY)

        if isinstance(configured_path, str) or configured_path is None:
            try:
                self.load(configured_path)
            except CdCertStoreException:
                self._cd_cert = None
                self._cd_cert_path = None
                Settings.clear(self.CD_CERT_PATH_KEY)
        else:
            Settings.clear(self.CD_CERT_PATH_KEY)

    @property
    def cd_cert(self) -> Optional[bytes]:
        """Return loaded CD certificate bytes."""
        return self._cd_cert

    @property
    def cd_cert_path(self) -> Optional[str]:
        """Return loaded CD certificate path as string."""
        return str(self._cd_cert_path) if self._cd_cert_path else None

    @classmethod
    def expected_formats(cls) -> list[str]:
        """Return supported file extensions for UI usage."""
        return list(cls._EXPECTED_FORMATS)

    def load(self, path: Optional[str]) -> None:
        """
        Load CD certificate from a path.

        Path must point to an existing `.der` file.
        """
        if path is None:
            self._cd_cert = None
            self._cd_cert_path = None
            Settings.clear(self.CD_CERT_PATH_KEY)
            return

        resolved_path = Path(path).expanduser().resolve()

        if not resolved_path.is_file():
            raise CdCertStoreLoadError(
                "CD certificate load failed: file was not found or is not a "
                f"regular file. path='{resolved_path}'"
            )

        if resolved_path.suffix.lower() not in self._EXPECTED_FORMATS:
            raise CdCertStoreLoadError(
                "CD certificate load failed: unsupported file extension. "
                f"path='{resolved_path}', extension='{resolved_path.suffix}', "
                f"expected one of {', '.join(self._EXPECTED_FORMATS)}"
            )

        try:
            cd_cert = resolved_path.read_bytes()
        except Exception as exc:
            raise CdCertStoreLoadError(
                "CD certificate load failed: could not read certificate bytes "
                f"from disk. path='{path}', "
                f"reason='{type(exc).__name__}: {exc}'"
            ) from exc

        self._cd_cert = cd_cert
        self._cd_cert_path = resolved_path

        Settings.set(self.CD_CERT_PATH_KEY, str(resolved_path))


cd_cert_store = CdCertStore()
