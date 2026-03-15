from __future__ import annotations

import itertools

from .model import FactoryDataModel
from .status import FactoryStatusCode

from factory_transaction_pb2 import FactoryRequest, FactoryResponse
from factory_command_pb2 import FactoryWriteRequest
from factory_data_pb2 import FactoryData


class FactoryTransactionCodec:
    """Encode and decode factory protobuf transactions."""

    def __init__(self) -> None:
        self._tx_counter = itertools.count(1)

    def next_transaction_id(self) -> int:
        """Return the next transaction identifier."""
        return next(self._tx_counter)

    def encode_write_request(self, data: FactoryDataModel) -> tuple[int, bytes]:
        """Encode a FactoryWriteRequest transaction."""
        tx_id = self.next_transaction_id()

        request = FactoryRequest()
        request.transaction_id = tx_id

        write = FactoryWriteRequest()
        write.data.CopyFrom(self._encode_factory_data(data))

        request.write.CopyFrom(write)

        return tx_id, request.SerializeToString()

    def decode_response(self, payload: bytes) -> FactoryResponse:
        """Decode a FactoryResponse protobuf."""
        response = FactoryResponse()
        response.ParseFromString(payload)
        return response

    def extract_status(self, response: FactoryResponse) -> FactoryStatusCode:
        """Return the status code from a response."""
        return FactoryStatusCode(response.status)

    def _encode_factory_data(self, model: FactoryDataModel) -> FactoryData:
        """Convert internal model to protobuf FactoryData."""
        data = FactoryData()

        if model.serial_number is not None:
            data.serial_number = model.serial_number

        if model.manufactured_date is not None:
            data.manufactured_date = model.manufactured_date

        if model.vendor_id is not None:
            data.vendor_id = model.vendor_id

        if model.product_id is not None:
            data.product_id = model.product_id

        if model.dac_cert is not None:
            data.dac_cert = model.dac_cert

        if model.dac_public_key is not None:
            data.dac_public_key = model.dac_public_key

        if model.dac_private_key is not None:
            data.dac_private_key = model.dac_private_key

        if model.pai_cert is not None:
            data.pai_cert = model.pai_cert

        if model.certification_declaration is not None:
            data.certification_declaration = model.certification_declaration

        if model.onboarding_payload is not None:
            data.onboarding_payload = model.onboarding_payload

        if model.spake2p_passcode is not None:
            data.spake2p_passcode = model.spake2p_passcode

        if model.spake2p_salt is not None:
            data.spake2p_salt = model.spake2p_salt

        if model.spake2p_iteration_count is not None:
            data.spake2p_iteration_count = model.spake2p_iteration_count

        if model.spake2p_verifier is not None:
            data.spake2p_verifier = model.spake2p_verifier

        return data
