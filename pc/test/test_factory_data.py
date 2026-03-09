from __future__ import annotations

import base64
import json
from pathlib import Path

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import serialization

from factory_data import (
    DeviceIdentityRetriever,
    FactoryDataProvider,
    ManufacturingDataRetriever,
    MatterAttestationDataRetriever,
    MatterOnboardingDataRetriever,
)
from matter.attestation_store import CdStore, DacCredentialPoolStore, PaiCertStore


# These PEM samples are derived from the example material discussed earlier.
DAC_CERT_PEM = """-----BEGIN CERTIFICATE-----
MIIB5zCCAY2gAwIBAgIQSfcKwMBN3rPkflj31HnZCjAKBggqhkjOPQQDAjA6MSIw
IAYDVQQDDBlMR0UgTWF0dGVyIElvVCBUaGluZ3MgUEFJMRQwEgYKKwYBBAGConwC
AQwEMTAyRTAgFw0yNTEyMDEwNTM1MzlaGA85OTk5MTIzMTE0NTk1OVowTTEfMB0G
A1UEAwwWRG9vcmxvY2soMjUxMjAxXzAwMDAxKTEUMBIGCisGAQQBgqJ8AgEMBDEw
MkUxFDASBgorBgEEAYKifAICDAQyMkMwMFkwEwYHKoZIzj0CAQYIKoZIzj0DAQcD
QgAErDhhCY1LKdB8YHLZ5hc97cclRXWk69/2cWmq3uoxrzQ7EwvVGQzwzzXK7noQ
PeF8GVOdKXTogvqD1MI8BuzVUqNgMF4wHwYDVR0jBBgwFoAU/a7tZgWILTIsb4tj
C0lB8xhAM4owHQYDVR0OBBYEFJbqM5vrMMswH8GCk9Zku1RZqz+SMA4GA1UdDwEB
/wQEAwIHgDAMBgNVHRMBAf8EAjAAMAoGCCqGSM49BAMCA0gAMEUCIQCYjw+C8xtn
CD6T2xIhp7p7j/qYITBIAFl8cYIEoDvUsAIgMoDzvXZQFuhI6l8s+AM4SlgtKrgw
wsv3X3lT1L6gfRk=
-----END CERTIFICATE-----
""".replace(" ", "").replace("\n\n", "\n")

# The above certificate text may not always parse if manually edited.
# A stable test strategy is to generate PEM files from DER-like artifacts already
# stored by the developer, but for now we keep the test focused on structure.


DAC_KEY_PEM = """-----BEGIN EC PRIVATE KEY-----
MHcCAQEEIPPZ5TNaH1khMvHW9Ebbyu97RXE8jN+oR0kDQi51wNlHoAoGCCqGSM49
AwEHoUQDQgAErDhhCY1LKdB8YHLZ5hc97cclRXWk69/2cWmq3uoxrzQ7EwvVGQzw
zzXK7noQPeF8GVOdKXTogvqD1MI8BuzVUg==
-----END EC PRIVATE KEY-----
""".replace(" ", "").replace("\n\n", "\n")

PAI_CERT_PEM = """-----BEGIN CERTIFICATE-----
MIIB7TCCAZOgAwIBAgIUDPQMAgnbeRCxJBSh7IMVPwoERcgwCgYIKoZIzj0EAwIw
STELMAkGA1UEBhMCS1IxITAfBgNVBAoMGERyZWFtIFNlY3VyaXR5IENvLiwgTHRk
LjEXMBUGA1UEAwwORFNDIE1hdHRlciBQQUEwIBcNMjQwNjEwMDM1NzMyWhgPOTk5
OTEyMzExNDU5NTlaMDoxIjAgBgNVBAMMGUxHRSBNYXR0ZXIgSW9UIFRoaW5ncyBQ
QUkxFDASBgorBgEEAYKifAIBDAQxMDJFMFkwEwYHKoZIzj0CAQYIKoZIzj0DAQcD
QgAEK/fczgm0XgjECRGvytufkMi73RY6sp9OMz/xXqAqaJ9drHYBgxPyo6wEbmW0
C4k15i8fVQhZnDoAwF6dmmlSu6NmMGQwHwYDVR0jBBgwFoAUSvBR2pNudxvmFRNx
KN5AJTNeaY0wHQYDVR0OBBYEFP2u7WYFiC0yLG+LYwtJQfMYQDOKMA4GA1UdDwEB
/wQEAwIBBjASBgNVHRMBAf8ECDAGAQH/AgEAMAoGCCqGSM49BAMCA0gAMEUCID0G
1qEioCwUkgkV/anOdHmnNyZ/CYlVfyNRUVnpGTJkAiEAvi9IA9jDKQSlEdqHy71l
IPydEl6c4OSaQW/yYgaCea4=
-----END CERTIFICATE-----
""".replace(" ", "").replace("\n\n", "\n")


CD_DER_BYTES = bytes([
    0x30, 0x82, 0x02, 0x19, 0x06, 0x09, 0x2A, 0x86,
    0x48, 0x86, 0xF7, 0x0D, 0x01, 0x07, 0x02, 0xA0,
])


def _write_text(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def _write_bytes(path: Path, data: bytes) -> None:
    path.write_bytes(data)


def _make_schema_dir(tmp_path: Path) -> Path:
    schema_dir = tmp_path / "schema"
    schema_dir.mkdir()

    base_schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "Base Matter Factory Data",
        "type": "object",
        "properties": {
            "serial_number": {"type": "string"},
            "manufactured_date": {"type": "string", "pattern": "^\\d{8}$"},
            "vendor_id": {"type": "integer"},
            "product_id": {"type": "integer"},
            "custom_flow": {"type": "integer"},
            "discovery_capabilities": {"type": "integer"},
            "dac_cert": {"type": "string"},
            "dac_public_key": {"type": "string"},
            "dac_private_key": {"type": "string"},
            "pai_cert": {"type": "string"},
            "certification_declaration": {"type": "string"},
            "spake2p_passcode": {"type": "integer"},
            "spake2p_salt": {"type": "string"},
            "spake2p_iteration_count": {"type": "integer"},
            "spake2p_verifier": {"type": "string"},
            "onboarding_payload": {"type": "string"},
        },
        "additionalProperties": False,
    }

    doorlock_schema = {
        "title": "Doorlock Factory Data",
        "required": [
            "serial_number",
            "manufactured_date",
            "dac_cert",
            "dac_public_key",
            "dac_private_key",
            "pai_cert",
            "certification_declaration",
            "spake2p_passcode",
            "spake2p_salt",
            "spake2p_iteration_count",
            "spake2p_verifier",
            "onboarding_payload",
        ],
        "properties": {
            "vendor_id": {"const": 4142},
            "product_id": {"const": 8896},
            "custom_flow": {"const": 0},
            "discovery_capabilities": {"const": 2},
            "spake2p_iteration_count": {"const": 1000},
        },
    }

    _write_text(schema_dir / "base.schema.json", json.dumps(base_schema, indent=2))
    _write_text(schema_dir / "doorlock.schema.json", json.dumps(doorlock_schema, indent=2))
    return schema_dir


@pytest.fixture
def schema_dir(tmp_path: Path) -> Path:
    return _make_schema_dir(tmp_path)


@pytest.fixture
def dac_dir(tmp_path: Path) -> Path:
    d = tmp_path / "dac"
    d.mkdir()

    _write_text(d / "LGE_Matter_IoT_Doorlock_260227_00001_Cert.pem", DAC_CERT_PEM)
    _write_text(d / "LGE_Matter_IoT_Doorlock_260227_00001_Key.pem", DAC_KEY_PEM)

    return d


@pytest.fixture
def pai_file(tmp_path: Path) -> Path:
    path = tmp_path / "pai.pem"
    _write_text(path, PAI_CERT_PEM)
    return path


@pytest.fixture
def cd_file(tmp_path: Path) -> Path:
    path = tmp_path / "cd.der"
    _write_bytes(path, CD_DER_BYTES)
    return path


def test_dac_pool_store_pull_report_flow(dac_dir: Path):
    store = DacCredentialPoolStore()
    store.set_directory(dac_dir)

    report = store.get_inventory_report()
    assert report.total == 1
    assert report.ready == 1
    assert report.consumed == 0
    assert report.error == 0

    material = store.pull()
    assert material.base_name == "LGE_Matter_IoT_Doorlock_260227_00001"
    assert isinstance(material.dac_cert_der, bytes)
    assert isinstance(material.dac_public_key, bytes)
    assert isinstance(material.dac_private_key, bytes)

    store.report(is_success=True)

    report = store.get_inventory_report()
    assert report.total == 1
    assert report.ready == 0
    assert report.consumed == 1
    assert report.error == 0


def test_pai_and_cd_store_load(pai_file: Path, cd_file: Path):
    pai_store = PaiCertStore()
    cd_store = CdStore()

    pai_store.set_file(pai_file)
    cd_store.set_file(cd_file)

    pai_der = pai_store.get_der()
    cd_der = cd_store.get_der()

    assert isinstance(pai_der, bytes)
    assert len(pai_der) > 0
    assert isinstance(cd_der, bytes)
    assert cd_der == CD_DER_BYTES


def test_onboarding_retriever_fetch(schema_dir: Path):
    provider = FactoryDataProvider(
        schema_directory=schema_dir,
        model_name="doorlock",
        retrievers=[
            MatterOnboardingDataRetriever(),
        ],
    )

    schema = provider.get_resolved_schema()
    data = MatterOnboardingDataRetriever().fetch(schema)

    assert "spake2p_passcode" in data
    assert "spake2p_salt" in data
    assert "spake2p_iteration_count" in data
    assert "spake2p_verifier" in data
    assert "onboarding_payload" in data

    assert isinstance(data["spake2p_passcode"], int)
    assert isinstance(data["spake2p_salt"], str)
    assert data["spake2p_iteration_count"] == 1000
    assert isinstance(data["spake2p_verifier"], str)
    assert data["onboarding_payload"].startswith("MT:")


def test_manufacturing_retriever_fetch(schema_dir: Path):
    provider = FactoryDataProvider(
        schema_directory=schema_dir,
        model_name="doorlock",
        retrievers=[],
    )
    schema = provider.get_resolved_schema()

    data = ManufacturingDataRetriever().fetch(schema)

    assert "manufactured_date" in data
    assert isinstance(data["manufactured_date"], str)
    assert len(data["manufactured_date"]) == 8
    assert data["manufactured_date"].isdigit()


def test_device_identity_retriever_fetch(schema_dir: Path):
    provider = FactoryDataProvider(
        schema_directory=schema_dir,
        model_name="doorlock",
        retrievers=[],
    )
    schema = provider.get_resolved_schema()

    retriever = DeviceIdentityRetriever()
    data = retriever.fetch(schema)

    assert "serial_number" in data
    assert isinstance(data["serial_number"], str)
    assert len(data["serial_number"]) >= 1


def test_provider_pull_and_report(
    schema_dir: Path,
    dac_dir: Path,
    pai_file: Path,
    cd_file: Path,
):
    dac_store = DacCredentialPoolStore()
    pai_store = PaiCertStore()
    cd_store = CdStore()

    dac_store.set_directory(dac_dir)
    pai_store.set_file(pai_file)
    cd_store.set_file(cd_file)

    provider = FactoryDataProvider(
        schema_directory=schema_dir,
        model_name="doorlock",
        retrievers=[
            DeviceIdentityRetriever(),
            ManufacturingDataRetriever(),
            MatterAttestationDataRetriever(
                dac_store=dac_store,
                pai_store=pai_store,
                cd_store=cd_store,
            ),
            MatterOnboardingDataRetriever(),
        ],
    )

    data = provider.pull()

    assert "serial_number" in data
    assert "manufactured_date" in data
    assert "dac_cert" in data
    assert "dac_public_key" in data
    assert "dac_private_key" in data
    assert "pai_cert" in data
    assert "certification_declaration" in data
    assert "spake2p_passcode" in data
    assert "spake2p_salt" in data
    assert "spake2p_iteration_count" in data
    assert "spake2p_verifier" in data
    assert "onboarding_payload" in data

    assert isinstance(data["dac_cert"], str)
    assert isinstance(data["dac_public_key"], str)
    assert isinstance(data["dac_private_key"], str)
    assert isinstance(data["pai_cert"], str)
    assert isinstance(data["certification_declaration"], str)
    assert data["onboarding_payload"].startswith("MT:")

    provider.report(is_success=True)

    report = dac_store.get_inventory_report()
    assert report.consumed == 1