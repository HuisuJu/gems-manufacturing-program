from __future__ import annotations

from typing import AbstractSet, Any

import storage

from ..retriever import Retriever, RetrieverError
from ..schema import FactoryDataSchema


class MatterAttestationDataRetriever(Retriever):
    """Matter Attestation Data Retriever."""

    _SUPPORTED_FIELDS = frozenset(
        {
            "dac_cert",
            "dac_public_key",
            "dac_private_key",
            "pai_cert",
            "cd_cert",
        }
    )

    def __init__(self) -> None:
        self._dac_pull_report_pending = False
        self._dac_material_base_name: str | None = None

    @property
    def name(self) -> str:
        """Return the retriever name."""
        return "matter_attestation"

    @property
    def supported_fields(self) -> AbstractSet[str]:
        """Return supported fields."""
        return self._SUPPORTED_FIELDS

    def fetch(self, schema: FactoryDataSchema) -> dict[str, Any]:
        """Return requested attestation fields."""
        target_fields = self.target_fields(schema)
        self._dac_pull_report_pending = False
        self._dac_material_base_name = None

        if not target_fields:
            return {}

        result: dict[str, Any] = {}

        if any(
            field in target_fields
            for field in ("dac_cert", "dac_public_key", "dac_private_key")
        ):
            result.update(self._fetch_dac_materials(target_fields))

        if "pai_cert" in target_fields:
            result["pai_cert"] = self._fetch_pai_cert()

        if "cd_cert" in target_fields:
            result["cd_cert"] = self._fetch_cd_cert()

        return result

    def report(self, is_success: bool) -> None:
        """Report DAC pull result."""
        if not self._dac_pull_report_pending:
            return

        if self._dac_material_base_name is None:
            self._dac_pull_report_pending = False
            raise RetrieverError("No DAC material is pending for report.")

        try:
            storage.dac_pool_store.set_material_state(
                base_name=self._dac_material_base_name,
                is_success=is_success,
            )
        except Exception as exc:
            raise RetrieverError("Failed to report Matter attestation result.") from exc
        finally:
            self._dac_pull_report_pending = False
            self._dac_material_base_name = None

    def _fetch_dac_materials(self, target_fields: AbstractSet[str]) -> dict[str, Any]:
        """Return DAC certificate/key pair."""
        try:
            base_name, dac_material = storage.dac_pool_store.get_material()
        except Exception as exc:
            raise RetrieverError("Failed to get a DAC certificate/key pair.") from exc

        self._dac_material_base_name = base_name
        self._dac_pull_report_pending = True

        result: dict[str, Any] = {}

        if "dac_cert" in target_fields:
            result["dac_cert"] = dac_material.cert_der.hex()

        if "dac_public_key" in target_fields:
            result["dac_public_key"] = dac_material.public_key.hex()

        if "dac_private_key" in target_fields:
            result["dac_private_key"] = dac_material.private_key.hex()

        return result

    def _fetch_pai_cert(self) -> str:
        """Return PAI certificate."""
        try:
            pai_der = storage.pai_cert_store.cert()
        except Exception as exc:
            raise RetrieverError("Failed to get the PAI certificate.") from exc

        return pai_der.hex()

    def _fetch_cd_cert(self) -> str:
        """Return CD certificate."""
        try:
            cd_der = storage.cd_cert_store.cert()
        except Exception as exc:
            raise RetrieverError(
                "Failed to get the Certification Declaration."
            ) from exc

        if cd_der is None:
            raise RetrieverError("Certification Declaration is not available.")

        return cd_der.hex()
