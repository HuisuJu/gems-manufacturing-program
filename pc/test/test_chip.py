import base64
import os

import pytest

from chip.spake2p import generate_verifier
from chip.SetupPayload import SetupPayload, CommissioningFlow


PASSCODE = 20202021
ITERATION_COUNT = 1000
DISCRIMINATOR = 3840


def test_spake2p_verifier_generation():
    salt = os.urandom(32)

    verifier = generate_verifier(PASSCODE, salt, ITERATION_COUNT)

    assert isinstance(verifier, bytes)
    assert len(verifier) > 0

    verifier_b64 = base64.b64encode(verifier).decode()
    salt_b64 = base64.b64encode(salt).decode()

    assert isinstance(verifier_b64, str)
    assert isinstance(salt_b64, str)


def test_onboarding_payload_generation():
    payload = SetupPayload(
        discriminator=DISCRIMINATOR,
        pincode=PASSCODE,
        rendezvous=4,
        flow=CommissioningFlow.Standard,
        vid=0,
        pid=0,
    )

    qr_code = payload.generate_qrcode()
    manual_code = payload.generate_manualcode()

    assert qr_code.startswith("MT:")
    assert isinstance(manual_code, str)
    assert len(manual_code) in (11, 21)


def test_qrcode_roundtrip():
    payload = SetupPayload(
        discriminator=DISCRIMINATOR,
        pincode=PASSCODE,
        rendezvous=4,
        flow=CommissioningFlow.Standard,
        vid=0,
        pid=0,
    )

    qr_code = payload.generate_qrcode()

    parsed = SetupPayload.parse(qr_code)

    assert parsed is not None
    assert parsed.pincode == PASSCODE
    assert parsed.long_discriminator == DISCRIMINATOR


def test_manualcode_roundtrip():
    payload = SetupPayload(
        discriminator=DISCRIMINATOR,
        pincode=PASSCODE,
        rendezvous=4,
        flow=CommissioningFlow.Standard,
        vid=0,
        pid=0,
    )

    manual_code = payload.generate_manualcode()

    parsed = SetupPayload.parse(manual_code)

    assert parsed is not None
    assert parsed.pincode == PASSCODE
    assert parsed.short_discriminator == (DISCRIMINATOR >> 8)