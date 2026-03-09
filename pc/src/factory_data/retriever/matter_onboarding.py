from __future__ import annotations

import base64
import secrets
from typing import Any, AbstractSet, Mapping

from chip.SetupPayload import CommissioningFlow, SetupPayload
from chip.spake2p import INVALID_PASSCODES, generate_verifier

from .base import Retriever, RetrieverError


PASSCODE_MIN = 0
PASSCODE_MAX = 99_999_999
DISCRIMINATOR_MIN = 0
DISCRIMINATOR_MAX = 0x0FFF

SPAKE2P_SALT_LENGTH = 32
SPAKE2P_ITERATION_COUNT = 1000


class MatterOnboardingDataRetriever(Retriever):
    """
    Generate Matter onboarding-related factory data.

    This retriever returns only the onboarding fields that are currently
    considered output data for factory provisioning:

    - spake2p_passcode
    - spake2p_salt
    - spake2p_iteration_count
    - spake2p_verifier
    - onboarding_payload

    The following schema fields are read as fixed input parameters for payload
    generation, but are not returned by this retriever:

    - vendor_id
    - product_id
    - custom_flow
    - discovery_capabilities

    The discriminator is generated internally and is used only during
    onboarding payload generation.
    """

    _SUPPORTED_FIELDS = frozenset({
        "spake2p_passcode",
        "spake2p_salt",
        "spake2p_iteration_count",
        "spake2p_verifier",
        "onboarding_payload",
    })

    @property
    def name(self) -> str:
        """
        Return the logical retriever name.
        """
        return "matter_onboarding"

    @property
    def supported_fields(self) -> AbstractSet[str]:
        """
        Return the field names that this retriever may return.

        Fields used only as schema-driven input parameters are intentionally
        excluded from this set.
        """
        return self._SUPPORTED_FIELDS

    def fetch(self, schema: Mapping[str, Any]) -> dict[str, Any]:
        """
        Generate and return Matter onboarding-related fields requested by
        the schema.

        This retriever reads vendor_id, product_id, custom_flow, and
        discovery_capabilities from the schema as input parameters for QR
        payload generation, but it does not return them.

        Args:
            schema: Factory data schema represented as a Python mapping.

        Returns:
            A flat dictionary containing the onboarding fields produced by this
            retriever.

        Raises:
            RetrieverError: If required schema information is missing or the
                onboarding data cannot be generated.
        """
        required_fields = self._get_required_fields(schema)
        target_fields = required_fields & set(self.supported_fields)

        if not target_fields:
            return {}

        vendor_id = self._get_const_int(schema, "vendor_id")
        product_id = self._get_const_int(schema, "product_id")
        custom_flow = self._get_const_int(schema, "custom_flow")
        discovery_capabilities = self._get_const_int(schema, "discovery_capabilities")

        passcode = self._generate_passcode()
        discriminator = self._generate_discriminator()
        salt = self._generate_salt()
        verifier = generate_verifier(
            passcode=passcode,
            salt=salt,
            iterations=SPAKE2P_ITERATION_COUNT,
        )
        onboarding_payload = self._generate_onboarding_payload(
            discriminator=discriminator,
            passcode=passcode,
            vendor_id=vendor_id,
            product_id=product_id,
            discovery_capabilities=discovery_capabilities,
            custom_flow=custom_flow,
        )

        result: dict[str, Any] = {}

        if "spake2p_passcode" in target_fields:
            result["spake2p_passcode"] = passcode

        if "spake2p_salt" in target_fields:
            result["spake2p_salt"] = base64.b64encode(salt).decode("ascii")

        if "spake2p_iteration_count" in target_fields:
            result["spake2p_iteration_count"] = SPAKE2P_ITERATION_COUNT

        if "spake2p_verifier" in target_fields:
            result["spake2p_verifier"] = base64.b64encode(verifier).decode("ascii")

        if "onboarding_payload" in target_fields:
            result["onboarding_payload"] = onboarding_payload

        return result

    def _get_required_fields(self, schema: Mapping[str, Any]) -> set[str]:
        """
        Return the top-level required field names declared by the schema.

        Args:
            schema: Factory data schema represented as a Python mapping.

        Returns:
            A set of required field names.

        Raises:
            RetrieverError: If the schema does not define the required field
                list.
        """
        required = schema.get("required")
        if not isinstance(required, list):
            raise RetrieverError(
                "Factory data schema is missing the top-level required field list."
            )

        return {field for field in required if isinstance(field, str)}

    def _get_const_int(self, schema: Mapping[str, Any], field_name: str) -> int:
        """
        Read an integer const value from the schema properties section.

        This helper is intended for schema-driven input parameters such as
        vendor_id and product_id.

        Args:
            schema: Factory data schema represented as a Python mapping.
            field_name: Name of the schema field.

        Returns:
            The integer const value declared for the field.

        Raises:
            RetrieverError: If the field does not define an integer const value.
        """
        properties = schema.get("properties")
        if not isinstance(properties, Mapping):
            raise RetrieverError("Factory data schema does not define top-level properties.")

        field_schema = properties.get(field_name)
        if not isinstance(field_schema, Mapping):
            raise RetrieverError(f"Factory data schema does not define the field '{field_name}'.")

        const_value = field_schema.get("const")
        if not isinstance(const_value, int):
            raise RetrieverError(
                f"Factory data schema field '{field_name}' must define an integer const value."
            )

        return const_value

    def _generate_passcode(self) -> int:
        """
        Generate a valid Matter SPAKE2+ passcode.

        The passcode is generated directly from a cryptographically secure
        random number generator in the range 0..99999999, and invalid
        passcodes defined by the Matter specification are rejected.

        Returns:
            A valid passcode represented as an integer.
        """
        while True:
            passcode = secrets.randbelow(PASSCODE_MAX + 1)
            if passcode not in INVALID_PASSCODES:
                return passcode

    def _generate_discriminator(self) -> int:
        """
        Generate a random Matter long discriminator.

        Returns:
            A discriminator in the range 0..4095.
        """
        return secrets.randbelow(DISCRIMINATOR_MAX + 1)

    def _generate_salt(self) -> bytes:
        """
        Generate a random SPAKE2+ salt.

        Returns:
            A random salt byte string of fixed length.
        """
        return secrets.token_bytes(SPAKE2P_SALT_LENGTH)

    def _generate_onboarding_payload(
        self,
        discriminator: int,
        passcode: int,
        vendor_id: int,
        product_id: int,
        discovery_capabilities: int,
        custom_flow: int,
    ) -> str:
        """
        Generate the Matter onboarding QR payload string.

        Args:
            discriminator: Long discriminator value.
            passcode: SPAKE2+ passcode.
            vendor_id: Matter Vendor ID read from the schema.
            product_id: Matter Product ID read from the schema.
            discovery_capabilities: Rendezvous capability bitmask read from
                the schema.
            custom_flow: Commissioning flow value read from the schema.

        Returns:
            The onboarding payload string beginning with 'MT:'.

        Raises:
            RetrieverError: If the payload cannot be generated.
        """
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
            raise RetrieverError("Failed to generate the Matter onboarding payload.") from exc