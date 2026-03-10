"""Thermostat provisioning dispatcher.

This dispatcher sends thermostat factory data records over a connected raw
stream.

Each record uses the thermostat-side temporary format:

    - 1 byte: item index
    - 2 bytes: payload length
    - N bytes: payload

Dispatcher readiness is defined only by the underlying stream connection
state. If the stream is connected, the dispatcher is considered ready.
"""

from __future__ import annotations


from typing import Any, Callable, NamedTuple

from stream import Stream

from provision.dispatcher import DispatchResult, ProvisionDispatcher


class ThermostatDispatcherError(Exception):
    """
    Base exception for thermostat dispatcher failures.
    """


class ThermostatDispatcherConfigurationError(ThermostatDispatcherError):
    """
    Raised when required factory data is missing or invalid.
    """


class _DispatchItem(NamedTuple):
    """
    One thermostat dispatch item definition.
    """

    index: int
    key_candidates: tuple[str, ...]
    required: bool
    value_kind: str
    description: str


class ThermostatDispatcher(ProvisionDispatcher):
    """
    Dispatcher implementation for the thermostat provisioning format.
    """

    _ITEMS: tuple[_DispatchItem, ...] = (
        _DispatchItem(
            index=0,
            key_candidates=("cd", "certification_declaration"),
            required=True,
            value_kind="bytes",
            description="Certification Declaration",
        ),
        _DispatchItem(
            index=1,
            key_candidates=("pai_cert", "pai_certificate"),
            required=True,
            value_kind="bytes",
            description="PAI certificate",
        ),
        _DispatchItem(
            index=2,
            key_candidates=("dac_cert", "dac_certificate"),
            required=True,
            value_kind="bytes",
            description="DAC certificate",
        ),
        _DispatchItem(
            index=3,
            key_candidates=("dac_private_key", "dac_priv", "dac_key"),
            required=False,
            value_kind="bytes",
            description="DAC private key",
        ),
        _DispatchItem(
            index=4,
            key_candidates=("dac_public_key", "dac_pub"),
            required=False,
            value_kind="bytes",
            description="DAC public key",
        ),
        _DispatchItem(
            index=5,
            key_candidates=(
                "iteration_count",
                "iterations",
                "spake2p_iteration_count",
            ),
            required=True,
            value_kind="u32",
            description="SPAKE2+ iteration count",
        ),
        _DispatchItem(
            index=6,
            key_candidates=("passcode", "setup_passcode", "spake2p_passcode"),
            required=True,
            value_kind="u32",
            description="SPAKE2+ passcode",
        ),
        _DispatchItem(
            index=7,
            key_candidates=("salt", "spake2p_salt"),
            required=True,
            value_kind="bytes",
            description="SPAKE2+ salt",
        ),
        _DispatchItem(
            index=8,
            key_candidates=("verifier_w0", "spake2p_verifier_w0"),
            required=False,
            value_kind="bytes",
            description="SPAKE2+ verifier W0",
        ),
        _DispatchItem(
            index=9,
            key_candidates=("verifier_l", "spake2p_verifier_l"),
            required=False,
            value_kind="bytes",
            description="SPAKE2+ verifier L",
        ),
    )

    def __init__(
        self,
        stream: Stream,
        ready_listener: Callable[[bool], None] | None = None,
    ) -> None:
        """
        Initialize the thermostat dispatcher.

        Args:
            stream:
                Raw byte stream used for transport.
            ready_listener:
                Callback invoked when dispatcher readiness changes.
        """
        super().__init__(ready_listener=ready_listener)
        self._stream = stream
        self._stream.subscribe_event(self._on_stream_event)
        self.notify_ready_changed(self.is_ready())

    def destroy(self) -> None:
        """
        Release owned subscriptions.
        """
        self._stream.unsubscribe_event(self._on_stream_event)

    def is_ready(self) -> bool:
        """
        Return whether the dispatcher is currently ready.

        Returns:
            True if the underlying stream is connected.
        """
        return self._stream.is_connected()

    def dispatch(self, factory_data: dict[str, Any]) -> DispatchResult:
        """
        Deliver one complete factory data payload to the thermostat target.

        Args:
            factory_data:
                Complete factory data dictionary.

        Returns:
            DispatchResult describing the outcome.
        """
        if not isinstance(factory_data, dict):
            raise ThermostatDispatcherConfigurationError(
                "The factory data payload must be a dictionary."
            )

        if not self.is_ready():
            return DispatchResult(
                success=False,
                message="The thermostat target is not connected.",
                details={"reason": "stream_not_connected"},
            )

        encoded_records: list[tuple[_DispatchItem, bytes]] = []
        skipped_optional: list[str] = []

        for item in self._ITEMS:
            raw_value = self._find_value(factory_data, item.key_candidates)

            if raw_value is None:
                if item.required:
                    return DispatchResult(
                        success=False,
                        message=(
                            "Required thermostat factory data is missing: "
                            f"{item.description}."
                        ),
                        details={
                            "reason": "missing_required_item",
                            "item_index": item.index,
                            "item_description": item.description,
                            "accepted_keys": list(item.key_candidates),
                        },
                    )

                skipped_optional.append(item.description)
                continue

            payload = self._encode_value(item, raw_value)
            record = self._build_record(item.index, payload)
            encoded_records.append((item, record))

        sent_indices: list[int] = []

        for item, record in encoded_records:
            if not self._stream.write(record):
                return DispatchResult(
                    success=False,
                    message=(
                        "Failed to send thermostat factory data item: "
                        f"{item.description}."
                    ),
                    details={
                        "reason": "stream_write_failed",
                        "item_index": item.index,
                        "item_description": item.description,
                        "sent_indices": sent_indices,
                    },
                )

            sent_indices.append(item.index)

        return DispatchResult(
            success=True,
            message="Thermostat factory data was dispatched successfully.",
            details={
                "sent_item_indices": sent_indices,
                "sent_item_count": len(sent_indices),
                "skipped_optional_items": skipped_optional,
            },
        )

    def _on_stream_event(self, event_name: str) -> None:
        """
        Propagate readiness changes from the underlying stream.
        """
        if event_name == "connected":
            self.notify_ready_changed(True)
        elif event_name == "disconnected":
            self.notify_ready_changed(False)

    def _find_value(
        self,
        factory_data: dict[str, Any],
        keys: tuple[str, ...],
    ) -> Any | None:
        """
        Return the first matching value from the given candidate keys.
        """
        for key in keys:
            if key in factory_data:
                return factory_data[key]
        return None

    def _encode_value(self, item: _DispatchItem, value: Any) -> bytes:
        """
        Encode one thermostat item payload.
        """
        if item.value_kind == "bytes":
            return self._encode_bytes(value, item.description)

        if item.value_kind == "u32":
            return self._encode_u32(value, item.description)

        raise ThermostatDispatcherConfigurationError(
            f"Unsupported thermostat item encoding kind: {item.value_kind}"
        )

    def _encode_bytes(self, value: Any, field_name: str) -> bytes:
        """
        Normalize one bytes-like value.

        Accepted forms:
            - bytes
            - bytearray
            - memoryview
            - hex string
        """
        if isinstance(value, bytes):
            return value

        if isinstance(value, bytearray):
            return bytes(value)

        if isinstance(value, memoryview):
            return bytes(value)

        if isinstance(value, str):
            normalized = value.strip().lower().replace(" ", "").replace("_", "")
            if normalized.startswith("0x"):
                normalized = normalized[2:]

            if not normalized:
                return b""

            try:
                return bytes.fromhex(normalized)
            except ValueError as exc:
                raise ThermostatDispatcherConfigurationError(
                    f"The value for '{field_name}' is not valid hex."
                ) from exc

        raise ThermostatDispatcherConfigurationError(
            f"The value for '{field_name}' must be bytes-like or a hex string."
        )

    def _encode_u32(self, value: Any, field_name: str) -> bytes:
        """
        Encode one unsigned 32-bit integer as a 4-byte little-endian payload.
        """
        if isinstance(value, bool) or not isinstance(value, int):
            raise ThermostatDispatcherConfigurationError(
                f"The value for '{field_name}' must be an integer."
            )

        if value < 0 or value > 0xFFFFFFFF:
            raise ThermostatDispatcherConfigurationError(
                f"The value for '{field_name}' is out of range for uint32."
            )

        return value.to_bytes(4, byteorder="little", signed=False)

    def _build_record(self, index: int, payload: bytes) -> bytes:
        """
        Build one thermostat transfer record.

        Layout:
            - index: 1 byte
            - length: 2 bytes
            - payload: N bytes
        """
        if index < 0 or index > 0xFF:
            raise ThermostatDispatcherConfigurationError(
                "The thermostat item index is out of range."
            )

        if len(payload) > 0xFFFF:
            raise ThermostatDispatcherConfigurationError(
                "The thermostat item payload is too large."
            )

        return (
            bytes((index,))
            + len(payload).to_bytes(2, byteorder="little", signed=False)
            + payload
        )
