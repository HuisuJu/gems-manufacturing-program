from __future__ import annotations

import base64
from typing import AbstractSet, Any, Mapping

import storage

from .base import Retriever, RetrieverError


class MatterAttestationDataRetriever(Retriever):
    """
    Retrieve Matter attestation factory data.
    """

    _SUPPORTED_FIELDS = frozenset(
        {
            "dac_cert",
            "dac_public_key",
            "dac_private_key",
            "pai_cert",
            "certification_declaration",
        }
    )

    @property
    def name(self) -> str:
        """
        Retriever name.
        """
        return "matter_attestation"

    @property
    def supported_fields(self) -> AbstractSet[str]:
        """
        Supported output fields.
        """
        return self._SUPPORTED_FIELDS

    def fetch(self, schema: Mapping[str, Any]) -> dict[str, Any]:
        """
        Fetch Matter attestation data for the requested schema fields.
        """
        target_fields = self.target_fields(schema)
        if not target_fields:
            return {}

        result: dict[str, Any] = {}
        dac_pulled = False

        try:
            if {
                "dac_cert",
                "dac_public_key",
                "dac_private_key",
            } & target_fields:
                result.update(self._fetch_dac_materials(target_fields))
                dac_pulled = True

            if "pai_cert" in target_fields:
                result.update(self._fetch_pai_cert())

            if "certification_declaration" in target_fields:
                result.update(self._fetch_cd_cert())

            return result

        except Exception:
            if dac_pulled:
                try:
                    storage.dac_pool_store.report(is_success=False)
                except Exception:
                    pass
            raise

    def report(self, is_success: bool) -> None:
        """
        Report DAC usage result.

        Args:
            is_success: True if provisioning succeeded, otherwise False.

        Raises:
            RetrieverError: Report failed.
        """
        try:
            storage.dac_pool_store.report(is_success=is_success)
        except Exception as exc:
            raise RetrieverError(
                "Failed to report the DAC credential pair result."
            ) from exc

    def _fetch_dac_materials(
        self,
        target_fields: AbstractSet[str],
    ) -> dict[str, Any]:
        """
        Fetch requested DAC-related fields from the DAC pool.
        """
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

    def _fetch_pai_cert(self) -> dict[str, Any]:
        """
        Fetch the PAI certificate.
        """
        try:
            pai_der = storage.pai_cert_store.get()
        except Exception as exc:
            raise RetrieverError(
                "Failed to get the PAI certificate."
            ) from exc

        return {
            "pai_cert": self._encode(pai_der),
        }

    def _fetch_cd_cert(self) -> dict[str, Any]:
        """
        Fetch the Certification Declaration.
        """
        try:
            cd_der = storage.cd_store.get()
        except Exception as exc:
            raise RetrieverError(
                "Failed to get the Certification Declaration."
            ) from exc

        return {
            "certification_declaration": self._encode(cd_der),
        }

    @staticmethod
    def _encode(value: bytes) -> str:
        """
        Encode bytes as Base64 ASCII.
        """
        return base64.b64encode(value).decode("ascii")