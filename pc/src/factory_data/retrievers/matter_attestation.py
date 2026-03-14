from __future__ import annotations

from typing import AbstractSet, Any

import storage

from ..retriever import Retriever, RetrieverError

from ..schema import FactoryDataSchema


class MatterAttestationDataRetriever(Retriever):
    """Retrieve Matter attestation fields."""

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

    @property

    def name(self) -> str:
        """Retriever name."""
        return "matter_attestation"

    @property

    def supported_fields(self) -> AbstractSet[str]:
        """Supported output fields."""
        return self._SUPPORTED_FIELDS

    def fetch(self, schema: FactoryDataSchema) -> dict[str, Any]:
        """Fetch required attestation fields."""
        target_fields = self.target_fields(schema)
        if not target_fields:
            self._dac_pull_report_pending = False
            return {}

        result: dict[str, Any] = {}
        self._dac_pull_report_pending = False

        if any(
            field in target_fields
            for field in ("dac_cert", "dac_public_key", "dac_private_key")
        ):
            result.update(self._fetch_dac_materials(target_fields))
            self._dac_pull_report_pending = True

        if "pai_cert" in target_fields:
            result["pai_cert"] = self._fetch_pai_cert()

        if "cd_cert" in target_fields:
            result["cd_cert"] = self._fetch_cd_cert()

        return result

    def report(self, is_success: bool) -> None:
        """Report the latest DAC pull result if pending."""
        if not self._dac_pull_report_pending:
            return

        try:
            storage.dac_pool_store.report(is_success=is_success)
        except Exception as exc:
            raise RetrieverError(
                "Failed to report Matter attestation result."
            ) from exc
        finally:
            self._dac_pull_report_pending = False

    def _fetch_dac_materials(
        self,
        target_fields: AbstractSet[str],
    ) -> dict[str, Any]:
        """Fetch requested DAC fields from the pool."""
        try:
            dac_material = storage.dac_pool_store.pull()
        except Exception as exc:
            raise RetrieverError(
                "Failed to pull a DAC certificate/key pair."
            ) from exc

        result: dict[str, Any] = {}

        if "dac_cert" in target_fields:
            result["dac_cert"] = self._encode(dac_material.dac_cert_der)

        if "dac_public_key" in target_fields:
            result["dac_public_key"] = self._encode(dac_material.dac_public_key)

        if "dac_private_key" in target_fields:
            result["dac_private_key"] = self._encode(dac_material.dac_private_key)

        return result

    def _fetch_pai_cert(self) -> str:
        """Fetch and encode the PAI certificate."""
        try:
            pai_der = storage.pai_cert_store.get()
        except Exception as exc:
            raise RetrieverError(
                "Failed to get the PAI certificate."
            ) from exc

        return self._encode(pai_der)

    def _fetch_cd_cert(self) -> str:
        """Fetch and encode the CD certificate."""
        try:
            cd_der = storage.cd_cert_store.get()
        except Exception as exc:
            raise RetrieverError(
                "Failed to get the Certification Declaration."
            ) from exc

        if cd_der is None:
            raise RetrieverError(
                "Certification Declaration is not available."
            )

        return self._encode(cd_der)

    @staticmethod

    def _encode(value: bytes) -> str:
        """Encode bytes as uppercase hex string."""
        return value.hex().upper()
