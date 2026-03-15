from __future__ import annotations

from typing import Any

from .model import FactoryDataModel


class FactoryDataMapper:
    """Convert input dictionaries into FactoryDataModel objects."""

    def from_dict(self, data: dict[str, Any]) -> FactoryDataModel:
        """Map dictionary fields to FactoryDataModel."""
        model = FactoryDataModel()

        model.serial_number = data.get("serial_number")
        model.manufactured_date = data.get("manufactured_date")

        model.vendor_id = data.get("vendor_id")
        model.product_id = data.get("product_id")

        model.dac_cert = data.get("dac_cert")
        model.dac_public_key = data.get("dac_public_key")
        model.dac_private_key = data.get("dac_private_key")
        model.pai_cert = data.get("pai_cert")
        model.certification_declaration = data.get("certification_declaration")

        model.onboarding_payload = data.get("onboarding_payload")
        model.spake2p_passcode = data.get("spake2p_passcode")
        model.spake2p_salt = data.get("spake2p_salt")
        model.spake2p_iteration_count = data.get("spake2p_iteration_count")
        model.spake2p_verifier = data.get("spake2p_verifier")

        return model
