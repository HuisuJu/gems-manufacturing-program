from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class FactoryDataModel:
    """Canonical Python representation of factory data."""

    serial_number: str | None = None
    manufactured_date: str | None = None

    vendor_id: int | None = None
    product_id: int | None = None

    dac_cert: bytes | None = None
    dac_public_key: bytes | None = None
    dac_private_key: bytes | None = None
    pai_cert: bytes | None = None
    certification_declaration: bytes | None = None

    onboarding_payload: bytes | None = None
    spake2p_passcode: int | None = None
    spake2p_salt: bytes | None = None
    spake2p_iteration_count: int | None = None
    spake2p_verifier: bytes | None = None
