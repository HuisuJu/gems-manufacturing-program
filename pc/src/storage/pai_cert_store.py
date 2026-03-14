from __future__ import annotations

from pathlib import Path

from cryptography import x509

from cryptography.hazmat.primitives import serialization

from system import Settings, SettingsItem


class PaiCertStore:
    """Store and provide one PAI certificate file."""

    def __init__(self) -> None:
        """Initialize store and load configured PAI path if available."""
        self.pai_cert: bytes | None = None

        configured_path = Settings.get(SettingsItem.PAI_FILE_PATH)
        self.load(configured_path)

    def get(self) -> bytes | None:
        """Return loaded PAI bytes."""
        return self.pai_cert

    def load(self, path: Path | None) -> None:
        """Load PAI bytes from a `.pem` file and save the path to settings."""
        if path is None:
            self.pai_cert = None
            Settings.clear(SettingsItem.PAI_FILE_PATH)
        else:
            try:
                pem_data = path.read_bytes()
                certificate = x509.load_pem_x509_certificate(pem_data)
                self.pai_cert = certificate.public_bytes(serialization.Encoding.DER)
            except Exception:
                self.pai_cert = None

            Settings.set(SettingsItem.PAI_FILE_PATH, path)

pai_cert_cert_store = PaiCertStore()
