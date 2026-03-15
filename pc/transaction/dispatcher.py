from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from frame.link import FrameLink
from frame.protocol import FrameError
from session.client import FactorySessionClient
from session.protocol import SessionError
from stream.base import Stream, StreamIOError
from transaction.client import FactoryClient
from transaction.mapper import FactoryDataMapper
from transaction.model import FactoryDataModel
from transaction.status import FactoryStatusError

from .error import (
    ProvisionError,
    ProvisionExecutionError,
    ProvisionProtocolError,
    ProvisionTransportError,
    ProvisionValidationError,
)


class ProvisionDispatcher(ABC):
    """Abstract base for provisioning dispatchers."""

    def __init__(self, stream: Stream) -> None:
        """Initialize dispatcher with a stream instance."""
        self._stream = stream

    @property
    def stream(self) -> Stream:
        """Return the underlying stream."""
        return self._stream

    @abstractmethod
    def dispatch(self, factory_data: dict[str, Any]) -> bool:
        """Dispatch one factory data payload. Returns True on success."""
        raise NotImplementedError


class GenericProvisionDispatcher(ProvisionDispatcher):
    """
    Generic provisioning dispatcher.

    This dispatcher is model-agnostic at the transport/protocol layer.
    It accepts a JSON-like dictionary, maps it to the internal factory model,
    opens a provisioning session, sends one write transaction, and returns
    True on success.
    """

    def __init__(
        self,
        stream: Stream,
        mapper: FactoryDataMapper | None = None,
    ) -> None:
        super().__init__(stream)
        self._mapper = mapper or FactoryDataMapper()

    @property
    def mapper(self) -> FactoryDataMapper:
        """Return the mapper used for input conversion."""
        return self._mapper

    def dispatch(self, factory_data: dict[str, Any]) -> bool:
        """
        Execute one provisioning write flow.

        Flow:
        1. validate/map input dictionary
        2. open session
        3. send FactoryWriteRequest
        4. validate FactoryResponse
        5. close session
        """
        model = self._map_input(factory_data)

        frame_link = FrameLink(self.stream)
        session_client = FactorySessionClient(frame_link)
        client = FactoryClient(session_client)

        opened = False

        try:
            client.open()
            opened = True

            client.write_factory_data(model)
            return True

        except FactoryStatusError as exc:
            raise ProvisionExecutionError(str(exc)) from exc

        except (SessionError, FrameError, StreamIOError) as exc:
            raise ProvisionTransportError(str(exc)) from exc

        except ValueError as exc:
            raise ProvisionProtocolError(str(exc)) from exc

        finally:
            if opened:
                try:
                    client.close()
                except Exception:
                    # Close failure should not mask the main result.
                    pass

    def _map_input(self, factory_data: dict[str, Any]) -> FactoryDataModel:
        """Validate and convert input dictionary into FactoryDataModel."""
        if not isinstance(factory_data, dict):
            raise ProvisionValidationError("factory_data must be a dictionary.")

        try:
            model = self.mapper.from_dict(factory_data)
        except Exception as exc:
            raise ProvisionValidationError("failed to map provisioning input.") from exc

        self._validate_model(model)
        return model

    def _validate_model(self, model: FactoryDataModel) -> None:
        """
        Perform light generic validation.

        This layer intentionally keeps validation minimal so that model-specific
        rules can later be added in custom mappers or specialized dispatchers.
        """
        if self._is_empty_model(model):
            raise ProvisionValidationError("factory_data does not contain any writable fields.")

        self._validate_optional_string(model.serial_number, "serial_number")
        self._validate_optional_string(model.manufactured_date, "manufactured_date")

        self._validate_optional_u32(model.vendor_id, "vendor_id")
        self._validate_optional_u32(model.product_id, "product_id")
        self._validate_optional_u32(model.spake2p_passcode, "spake2p_passcode")
        self._validate_optional_u32(model.spake2p_iteration_count, "spake2p_iteration_count")

        self._validate_optional_bytes(model.dac_cert, "dac_cert")
        self._validate_optional_bytes(model.dac_public_key, "dac_public_key")
        self._validate_optional_bytes(model.dac_private_key, "dac_private_key")
        self._validate_optional_bytes(model.pai_cert, "pai_cert")
        self._validate_optional_bytes(
            model.certification_declaration,
            "certification_declaration",
        )
        self._validate_optional_bytes(model.onboarding_payload, "onboarding_payload")
        self._validate_optional_bytes(model.spake2p_salt, "spake2p_salt")
        self._validate_optional_bytes(model.spake2p_verifier, "spake2p_verifier")

    @staticmethod
    def _is_empty_model(model: FactoryDataModel) -> bool:
        """Return whether all writable fields are None."""
        return all(
            value is None
            for value in (
                model.serial_number,
                model.manufactured_date,
                model.vendor_id,
                model.product_id,
                model.dac_cert,
                model.dac_public_key,
                model.dac_private_key,
                model.pai_cert,
                model.certification_declaration,
                model.onboarding_payload,
                model.spake2p_passcode,
                model.spake2p_salt,
                model.spake2p_iteration_count,
                model.spake2p_verifier,
            )
        )

    @staticmethod
    def _validate_optional_string(value: str | None, name: str) -> None:
        """Validate one optional string field."""
        if value is None:
            return
        if not isinstance(value, str):
            raise ProvisionValidationError(f"{name} must be a string.")

    @staticmethod
    def _validate_optional_bytes(value: bytes | None, name: str) -> None:
        """Validate one optional bytes field."""
        if value is None:
            return
        if not isinstance(value, (bytes, bytearray, memoryview)):
            raise ProvisionValidationError(f"{name} must be bytes-like.")

    @staticmethod
    def _validate_optional_u32(value: int | None, name: str) -> None:
        """Validate one optional uint32 field."""
        if value is None:
            return
        if not isinstance(value, int):
            raise ProvisionValidationError(f"{name} must be an integer.")
        if value < 0 or value > 0xFFFFFFFF:
            raise ProvisionValidationError(f"{name} must fit in uint32.")
    