from __future__ import annotations

import secrets
from typing import AbstractSet, Any

from chip.SetupPayload import CommissioningFlow, SetupPayload
from chip.spake2p import INVALID_PASSCODES, generate_verifier

from ..retriever import Retriever, RetrieverError
from ..schema import FactoryDataSchema


# Constants for Matter onboarding.
DISCRIMINATOR_MIN = 0
DISCRIMINATOR_MAX = 4095
PASSCODE_MIN = 0
PASSCODE_MAX = 99999998
SPAKE2P_VERIFIER_W0_SIZE = 32
SPAKE2P_VERIFIER_L_SIZE = 65
SPAKE2P_VERIFIER_TOTAL_SIZE = SPAKE2P_VERIFIER_W0_SIZE + SPAKE2P_VERIFIER_L_SIZE


class MatterOnboardingDataRetriever(Retriever):
    """Matter Onboarding Data Retriever."""

    _SUPPORTED_FIELDS = frozenset(
        {
            "discriminator",
            "spake2p_passcode",
            "spake2p_salt",
            "spake2p_iteration_count",
            "spake2p_verifier_w0",
            "spake2p_verifier_L",
            "onboarding_payload",
        }
    )

    @property
    def name(self) -> str:
        # Retriever key name
        return "matter_onboarding"

    @property
    def supported_fields(self) -> AbstractSet[str]:
        # Supported fields
        return self._SUPPORTED_FIELDS

    def fetch(self, schema: FactoryDataSchema) -> dict[str, Any]:
        # Generate requested onboarding fields
        target_fields = self.target_fields(schema)
        if not target_fields:
            return {}

        vendor_id = schema.get_integer("vendor_id")
        product_id = schema.get_integer("product_id")
        custom_flow = schema.get_integer("custom_flow")
        discovery_capabilities = schema.get_integer("discovery_capabilities")
        iteration_count = schema.get_integer("spake2p_iteration_count")
        salt_length_bytes = schema.get_size("spake2p_salt")

        passcode = self._generate_passcode()
        discriminator = self._generate_discriminator()
        salt = self._generate_salt(salt_length_bytes)

        verifier = generate_verifier(
            passcode=passcode,
            salt=salt,
            iterations=iteration_count,
        )
        verifier_w0, verifier_l = self._split_verifier(verifier)

        onboarding_payload = self._generate_onboarding_payload(
            discriminator=discriminator,
            passcode=passcode,
            vendor_id=vendor_id,
            product_id=product_id,
            discovery_capabilities=discovery_capabilities,
            custom_flow=custom_flow,
        )

        result: dict[str, Any] = {}
        if "discriminator" in target_fields:
            result["discriminator"] = discriminator
        if "spake2p_passcode" in target_fields:
            result["spake2p_passcode"] = passcode
        if "spake2p_salt" in target_fields:
            result["spake2p_salt"] = salt.hex().upper()
        if "spake2p_iteration_count" in target_fields:
            result["spake2p_iteration_count"] = iteration_count
        if "spake2p_verifier_w0" in target_fields:
            result["spake2p_verifier_w0"] = verifier_w0
        if "spake2p_verifier_L" in target_fields:
            result["spake2p_verifier_L"] = verifier_l
        if "onboarding_payload" in target_fields:
            result["onboarding_payload"] = onboarding_payload
        return result

    def report(self, is_success: bool) -> None:
        # No-op report
        _ = is_success

    def _generate_passcode(self) -> int:
        # Generate random valid SPAKE2+ passcode
        while True:
            passcode = PASSCODE_MIN + secrets.randbelow(PASSCODE_MAX - PASSCODE_MIN + 1)
            if passcode not in INVALID_PASSCODES:
                return passcode

    def _generate_discriminator(self) -> int:
        # Generate random discriminator
        return DISCRIMINATOR_MIN + secrets.randbelow(
            DISCRIMINATOR_MAX - DISCRIMINATOR_MIN + 1
        )

    def _generate_salt(self, length_bytes: int) -> bytes:
        # Generate random SPAKE2+ salt
        if length_bytes <= 0:
            raise RetrieverError("SPAKE2+ salt length must be positive.")
        return secrets.token_bytes(length_bytes)

    def _split_verifier(self, verifier: bytes) -> tuple[str, str]:
        # Split SPAKE2+ verifier into W0/L hex strings
        if len(verifier) != SPAKE2P_VERIFIER_TOTAL_SIZE:
            raise RetrieverError("SPAKE2+ verifier has an unexpected length.")
        verifier_w0 = verifier[:SPAKE2P_VERIFIER_W0_SIZE].hex().upper()
        verifier_l = verifier[SPAKE2P_VERIFIER_W0_SIZE:].hex().upper()
        return verifier_w0, verifier_l

    def _generate_onboarding_payload(
        self,
        discriminator: int,
        passcode: int,
        vendor_id: int,
        product_id: int,
        discovery_capabilities: int,
        custom_flow: int,
    ) -> str:
        # Generate Matter onboarding payload
        try:
            flow = CommissioningFlow(custom_flow)
        except ValueError as exc:
            raise RetrieverError(
                f"Unsupported commissioning flow value in schema: {custom_flow}."
            ) from exc
        try:
            payload = SetupPayload(
                discriminator=discriminator,
                pincode=passcode,
                rendezvous=discovery_capabilities,
                flow=flow,
                vid=vendor_id,
                pid=product_id,
            )
            return payload.generate_qrcode()
        except Exception as exc:
            raise RetrieverError(
                "Failed to generate the Matter onboarding payload."
            ) from exc
