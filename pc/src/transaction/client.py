from __future__ import annotations

from session.client import FactorySessionClient

from .model import FactoryDataModel
from .status import raise_for_status
from .transaction import FactoryTransactionCodec


class FactoryClient:
    """High-level client performing factory read/write transactions."""

    def __init__(
        self,
        session_client: FactorySessionClient,
        codec: FactoryTransactionCodec | None = None,
    ) -> None:
        self._session = session_client
        self._codec = codec or FactoryTransactionCodec()

    def open(self) -> None:
        """Open the session."""
        self._session.open()

    def close(self) -> None:
        """Close the session."""
        self._session.close()

    def write_factory_data(self, data: FactoryDataModel) -> None:
        """Send FactoryWriteRequest and validate the response."""
        tx_id, payload = self._codec.encode_write_request(data)

        self._session.send_message(payload)
        response_payload = self._session.receive_message()

        response = self._codec.decode_response(response_payload)

        if response.transaction_id != tx_id:
            raise RuntimeError("transaction_id mismatch in factory response.")

        status = self._codec.extract_status(response)
        raise_for_status(status)