from __future__ import annotations

import base64

from typing import Any, AbstractSet, Mapping

from logger import Logger, LogLevel

from storage import (
    CdStore,
    DacCredentialPoolStore,
    PaiCertStore,
)

from .base import Retriever, RetrieverError


class MatterAttestationDataRetriever(Retriever):
    """
    Retrieve Matter attestation factory data.
    """

    _SUPPORTED_FIELDS = frozenset({
        "dac_cert",
        "dac_public_key",
        "dac_private_key",
        "pai_cert",
        "certification_declaration",
    })

    def __init__(
        self,
        dac_store: DacCredentialPoolStore,
        pai_store: PaiCertStore,
        cd_store: CdStore,
    ) -> None:
        """
        Initialize with attestation stores.

        Args:
            dac_store: DAC credential pool store.
            pai_store: PAI certificate store.
            cd_store: Certification Declaration store.
        """
        self._dac_store = dac_store
        self._pai_store = pai_store
        self._cd_store = cd_store

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
        Fetch requested attestation fields.

        Args:
            schema: Factory data schema represented as a Python mapping.

        Returns:
            Flat field-value mapping.

        Raises:
            RetrieverError: Fetch failed.
        """
        required_fields = self._get_required_fields(schema)
        target_fields = required_fields & set(self.supported_fields)

        if not target_fields:
            return {}

        result: dict[str, Any] = {}

        dac_material = None
        needs_dac_material = bool(
            {"dac_cert", "dac_public_key", "dac_private_key"} & target_fields
        )

        if needs_dac_material:
            try:
                dac_material = self._dac_store.pull()
            except Exception as exc:
                raise RetrieverError(
                    "Failed to pull a DAC certificate/key pair."
                ) from exc

        try:
            if "dac_cert" in target_fields:
                if dac_material is None:
                    raise RetrieverError(
                        "DAC certificate material is not available."
                    )
                result["dac_cert"] = self._encode_bytes(dac_material.dac_cert_der)

            if "dac_public_key" in target_fields:
                if dac_material is None:
                    raise RetrieverError("DAC public key material is not available.")
                result["dac_public_key"] = self._encode_bytes(
                    dac_material.dac_public_key
                )

            if "dac_private_key" in target_fields:
                if dac_material is None:
                    raise RetrieverError(
                        "DAC private key material is not available."
                    )
                result["dac_private_key"] = self._encode_bytes(
                    dac_material.dac_private_key
                )

            if "pai_cert" in target_fields:
                pai_der = self._pai_store.get()
                result["pai_cert"] = self._encode_bytes(pai_der)

            if "certification_declaration" in target_fields:
                cd_der = self._cd_store.get()
                result["certification_declaration"] = self._encode_bytes(cd_der)

            return result
        except Exception:
            if dac_material is not None:
                try:
                    self._dac_store.report(is_success=False)
                except Exception as rollback_exc:
                    Logger.write(
                        LogLevel.ALERT,
                        "DAC rollback(report=False) failed. "
                        "Check DAC pool state before retry. "
                        f"({type(rollback_exc).__name__}: {rollback_exc})",
                    )
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
            self._dac_store.report(is_success=is_success)
        except Exception as exc:
            raise RetrieverError(
                "Failed to report the DAC credential pair result."
            ) from exc

    def _get_required_fields(self, schema: Mapping[str, Any]) -> set[str]:
        """
        Return required field names from schema.

        Args:
            schema: Factory data schema represented as a Python mapping.

        Returns:
            A set of required field names.

        Raises:
            RetrieverError: Invalid schema format.
        """
        required = schema.get("required")
        if not isinstance(required, list):
            raise RetrieverError(
                "Factory data schema is missing the top-level required field list."
            )

        return {field for field in required if isinstance(field, str)}

    def _encode_bytes(self, value: bytes) -> str:
        """
        Encode bytes as Base64 ASCII.

        Args:
            value: Binary value to encode.

        Returns:
            Base64-encoded ASCII string.
        """
        return base64.b64encode(value).decode("ascii")
