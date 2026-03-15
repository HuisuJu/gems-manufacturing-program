from __future__ import annotations

from pathlib import Path
from typing import Optional

from cryptography import x509
from cryptography.hazmat.primitives import serialization

from system import Settings


class PaiCertStoreException(Exception):
    """Base exception for PAI certificate store errors."""


class PaiCertStoreLoadError(PaiCertStoreException):
    """Raised when loading the PAI certificate fails."""


class PaiCertStore:
    """Store and provide one PAI certificate."""

    PAI_CERT_PATH_KEY = "pai_cert_store"
    _EXPECTED_FORMATS = [".pem"]

    _cert: Optional[bytes]
    _cert_path: Optional[Path]
    _issuer_name: Optional[x509.Name]
    _authority_key_identifier: Optional[bytes]

    def __init__(self) -> None:
        """Initialize the store and load configured PAI if present."""
        self._cert = None
        self._cert_path = None
        self._issuer_name = None
        self._authority_key_identifier = None

        configured_path = Settings.get(self.PAI_CERT_PATH_KEY)
        if isinstance(configured_path, str) or configured_path is None:
            try:
                self.load(configured_path)
            except PaiCertStoreException:
                self._cert = None
                self._cert_path = None
                self._issuer_name = None
                self._authority_key_identifier = None
                Settings.clear(self.PAI_CERT_PATH_KEY)
        else:
            Settings.clear(self.PAI_CERT_PATH_KEY)

    @property
    def cert(self) -> Optional[bytes]:
        """Return loaded PAI certificate bytes in DER format."""
        return self._cert

    @property
    def cert_path(self) -> Optional[str]:
        """Return loaded PAI certificate path as string."""
        return str(self._cert_path) if self._cert_path else None

    @property
    def issuer_name(self) -> Optional[x509.Name]:
        """Return issuer distinguished name."""
        return self._issuer_name

    @property
    def authority_key_identifier(self) -> Optional[bytes]:
        """Return Authority Key Identifier (AKI) key identifier."""
        return self._authority_key_identifier

    @classmethod
    def expected_formats(cls) -> list[str]:
        """Return supported file extensions for UI usage."""
        return list(cls._EXPECTED_FORMATS)

    def load(self, path: Optional[str]) -> None:
        """
        Load a PAI certificate from a `.pem` file.

        The certificate is stored internally in DER format.
        """
        if path is None:
            self._cert = None
            self._cert_path = None
            self._issuer_name = None
            self._authority_key_identifier = None
            Settings.clear(self.PAI_CERT_PATH_KEY)
            return

        resolved_path = Path(path).expanduser().resolve()

        if not resolved_path.is_file():
            raise PaiCertStoreLoadError(
                "PAI certificate load failed: file was not found or is not a "
                f"regular file. path='{resolved_path}'"
            )

        if resolved_path.suffix.lower() not in self._EXPECTED_FORMATS:
            raise PaiCertStoreLoadError(
                "PAI certificate load failed: unsupported file extension. "
                f"path='{resolved_path}', extension='{resolved_path.suffix}', "
                f"expected one of {', '.join(self._EXPECTED_FORMATS)}"
            )

        try:
            pem_data = resolved_path.read_bytes()
            certificate = x509.load_pem_x509_certificate(pem_data)
            der_cert = certificate.public_bytes(serialization.Encoding.DER)
            issuer = certificate.issuer

            try:
                aki_ext = certificate.extensions.get_extension_for_class(
                    x509.AuthorityKeyIdentifier
                ).value
                aki = aki_ext.key_identifier
            except x509.ExtensionNotFound:
                aki = None

        except Exception as exc:
            raise PaiCertStoreLoadError(
                "PAI certificate load failed: could not parse PEM certificate "
                f"or extract required fields. path='{path}', "
                f"reason='{type(exc).__name__}: {exc}'"
            ) from exc

        self._cert = der_cert
        self._cert_path = resolved_path
        self._issuer_name = issuer
        self._authority_key_identifier = aki

        Settings.set(self.PAI_CERT_PATH_KEY, str(resolved_path))


pai_cert_store = PaiCertStore()
