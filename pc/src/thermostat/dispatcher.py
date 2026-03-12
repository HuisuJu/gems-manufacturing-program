"""Thermostat provisioning dispatcher.

This dispatcher sends thermostat factory data records over a connected raw
stream.

Wire format for each transmitted item:
    b"se " + record + b"\\x0A"

Where record is:
    - 1 byte : item index
    - 2 bytes: payload length (little-endian)
    - N bytes: payload

Expected input format is a flat factory-data dictionary such as:

    {
        "certification_declaration": "<base64>",
        "pai_cert": "<base64>",
        "dac_cert": "<base64>",
        "dac_private_key": "<base64>",
        "dac_public_key": "<base64>",
        "spake2p_iteration_count": 1000,
        "spake2p_passcode": 88404584,
        "spake2p_salt": "<base64>",
        "spake2p_verifier": "<base64>",
        ...
    }

Binary values are decoded from base64 strings.
Integer values are encoded as 4-byte little-endian unsigned integers.

The combined SPAKE2+ verifier is split as:
    - W0: first 32 bytes
    - L : remaining 65 bytes

A background reader thread continuously reads from the stream and prints every
complete newline-terminated line received from the device.
"""

from __future__ import annotations

import base64

import threading

from typing import Any, Callable, NamedTuple

from logger.manager import Logger, LogLevel

from provision.dispatcher import DispatchResult, ProvisionDispatcher

from stream import Stream


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
    kind: str
    description: str


class ThermostatDispatcher(ProvisionDispatcher):
    """
    Dispatcher implementation for the thermostat provisioning format.
    """

    _READ_TIMEOUT_SEC = 0.1
    _SPAKE2P_W0_SIZE = 32
    _SPAKE2P_L_SIZE = 65
    _SPAKE2P_VERIFIER_SIZE = _SPAKE2P_W0_SIZE + _SPAKE2P_L_SIZE

    _COMMAND_PREFIX = b"se "
    _COMMAND_SUFFIX = b"\x0A"

    _ITEMS: tuple[_DispatchItem, ...] = (
        _DispatchItem(
            index=0,
            key_candidates=("cd", "certification_declaration"),
            required=True,
            kind="base64_bytes",
            description="Certification Declaration",
        ),
        _DispatchItem(
            index=1,
            key_candidates=("pai_cert", "pai_certificate"),
            required=True,
            kind="base64_bytes",
            description="PAI certificate",
        ),
        _DispatchItem(
            index=2,
            key_candidates=("dac_cert", "dac_certificate"),
            required=True,
            kind="base64_bytes",
            description="DAC certificate",
        ),
        _DispatchItem(
            index=3,
            key_candidates=("dac_private_key", "dac_priv", "dac_key"),
            required=True,
            kind="base64_bytes",
            description="DAC private key",
        ),
        _DispatchItem(
            index=4,
            key_candidates=("dac_public_key", "dac_pub"),
            required=True,
            kind="base64_bytes",
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
            kind="u32",
            description="SPAKE2+ iteration count",
        ),
        _DispatchItem(
            index=6,
            key_candidates=("passcode", "setup_passcode", "spake2p_passcode"),
            required=True,
            kind="u32",
            description="SPAKE2+ passcode",
        ),
        _DispatchItem(
            index=7,
            key_candidates=("salt", "spake2p_salt"),
            required=True,
            kind="base64_bytes",
            description="SPAKE2+ salt",
        ),
        _DispatchItem(
            index=8,
            key_candidates=("verifier_w0",),
            required=True,
            kind="base64_bytes",
            description="SPAKE2+ verifier W0",
        ),
        _DispatchItem(
            index=9,
            key_candidates=("verifier_l",),
            required=True,
            kind="base64_bytes",
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

        self._stop_event = threading.Event()
        self._rx_lock = threading.Lock()
        self._rx_buffer = bytearray()

        self._reader_thread = threading.Thread(
            target=self._reader_loop,
            name="ThermostatDispatcherReader",
            daemon=True,
        )
        self._reader_thread.start()

        self.notify_ready_changed(self.is_ready())

    def destroy(self) -> None:
        """
        Release owned subscriptions and stop the background reader thread.
        """
        self._stop_event.set()
        self._stream.unsubscribe_event(self._on_stream_event)

        if self._reader_thread.is_alive():
            self._reader_thread.join(timeout=1.0)

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
                Complete flat factory data dictionary.

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

        payload_source = dict(factory_data)
        self._expand_combined_verifier(payload_source)

        encoded_records: list[tuple[_DispatchItem, bytes]] = []
        skipped_optional: list[str] = []

        for item in self._ITEMS:
            raw_value = self._find_value(payload_source, item.key_candidates)

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
            frame = self._build_command_frame(record)
            self._log_raw_bytes("TX", frame)

            if not self._stream.write(frame):
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

            Logger.write(
                LogLevel.PROGRESS,
                f"Thermostat dispatch sent: idx={item.index}, "
                f"payload_len={len(record) - 3}, "
                f"frame_len={len(frame)}",
            )

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

    def _expand_combined_verifier(self, payload_source: dict[str, Any]) -> None:
        """
        Expand the combined SPAKE2+ verifier into W0 and L.

        The input JSON contains a single field:
            - spake2p_verifier

        This dispatcher converts it into:
            - verifier_w0 (first 32 bytes)
            - verifier_l  (remaining 65 bytes)

        The derived values are stored as base64 strings so they can be handled
        by the normal base64_bytes path.
        """
        if "verifier_w0" in payload_source and "verifier_l" in payload_source:
            return

        combined = self._find_value(payload_source, ("spake2p_verifier", "verifier"))
        if combined is None:
            raise ThermostatDispatcherConfigurationError(
                "Required thermostat factory data is missing: SPAKE2+ verifier."
            )

        verifier = self._decode_base64_bytes(combined, "SPAKE2+ verifier")

        if len(verifier) != self._SPAKE2P_VERIFIER_SIZE:
            raise ThermostatDispatcherConfigurationError(
                "The value for 'SPAKE2+ verifier' has an unexpected length."
            )

        w0 = verifier[: self._SPAKE2P_W0_SIZE]
        l_value = verifier[self._SPAKE2P_W0_SIZE :]

        payload_source["verifier_w0"] = base64.b64encode(w0).decode("ascii")
        payload_source["verifier_l"] = base64.b64encode(l_value).decode("ascii")

    def _encode_value(self, item: _DispatchItem, value: Any) -> bytes:
        """
        Encode one thermostat item payload.
        """
        if item.kind == "base64_bytes":
            return self._decode_base64_bytes(value, item.description)

        if item.kind == "u32":
            return self._encode_u32(value, item.description)

        raise ThermostatDispatcherConfigurationError(
            f"Unsupported thermostat item encoding kind: {item.kind}"
        )

    def _decode_base64_bytes(self, value: Any, field_name: str) -> bytes:
        """
        Decode one bytes-like or base64-string value into raw bytes.
        """
        if isinstance(value, bytes):
            return value

        if isinstance(value, bytearray):
            return bytes(value)

        if isinstance(value, memoryview):
            return bytes(value)

        if isinstance(value, str):
            normalized = "".join(value.strip().split())

            try:
                return base64.b64decode(normalized, validate=True)
            except Exception as exc:
                raise ThermostatDispatcherConfigurationError(
                    f"The value for '{field_name}' is not valid base64."
                ) from exc

        raise ThermostatDispatcherConfigurationError(
            f"The value for '{field_name}' must be bytes-like or a base64 string."
        )

    def _encode_u32(self, value: Any, field_name: str) -> bytes:
        """
        Encode one unsigned 32-bit integer as 4-byte little-endian.
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
            - length: 2 bytes, little-endian
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

    def _build_command_frame(self, record: bytes) -> bytes:
        """
        Build the final wire frame.

        Wire format:
            b"se " + record + b"\\x0A"
        """
        return self._COMMAND_PREFIX + record + self._COMMAND_SUFFIX

    def _reader_loop(self) -> None:
        """
        Continuously read raw chunks from the stream and print complete lines.

        Any device output terminated by '\\n' is printed immediately.
        """
        while not self._stop_event.is_set():
            try:
                chunk = self._stream.read(timeout=self._READ_TIMEOUT_SEC)
            except Exception as exc:
                Logger.write(
                    LogLevel.WARNING,
                    f"Thermostat dispatcher read failed: "
                    f"{type(exc).__name__}: {exc}",
                )
                continue

            if not chunk:
                continue

            if not isinstance(chunk, (bytes, bytearray, memoryview)):
                Logger.write(
                    LogLevel.WARNING,
                    "Thermostat dispatcher received non-bytes stream data.",
                )
                continue

            raw_chunk = bytes(chunk)
            self._log_raw_bytes("RX", raw_chunk)
            self._handle_rx_chunk(raw_chunk)

    def _log_raw_bytes(self, direction: str, payload: bytes) -> None:
        """
        Log raw serial payload in hexadecimal form.
        """
        Logger.write(
            LogLevel.PROGRESS,
            f"Thermostat raw {direction}: len={len(payload)} hex={payload.hex()}",
        )

    def _handle_rx_chunk(self, chunk: bytes) -> None:
        """
        Append a received chunk and log every complete newline-terminated line.
        """
        completed_lines: list[bytes] = []

        with self._rx_lock:
            self._rx_buffer.extend(chunk)

            while True:
                newline_pos = self._rx_buffer.find(b"\n")
                if newline_pos < 0:
                    break

                line = bytes(self._rx_buffer[:newline_pos])
                del self._rx_buffer[: newline_pos + 1]

                if line.endswith(b"\r"):
                    line = line[:-1]

                completed_lines.append(line)

        for line in completed_lines:
            text = self._decode_rx_line(line)
            Logger.write(LogLevel.PROGRESS, text)

    def _decode_rx_line(self, line: bytes) -> str:
        """
        Decode one RX line for logs without garbled replacement glyphs.

        - Normal UTF-8 text is returned as-is.
        - Invalid byte sequences are escaped as \\xNN.
        """
        try:
            return line.decode("utf-8")
        except UnicodeDecodeError:
            return line.decode("utf-8", errors="backslashreplace")
