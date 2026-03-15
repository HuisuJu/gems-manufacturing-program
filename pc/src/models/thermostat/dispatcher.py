"""Thermostat provisioning dispatcher.

Sends factory data records over stream as: b"se " + record + b"\n".
"""

from __future__ import annotations

import threading

from typing import Any, NamedTuple

from logger.manager import Logger, LogLevel

from provision.dispatcher import ProvisionDispatcher

from stream import Stream, StreamEvent


class ThermostatDispatcherError(Exception):
    """Base thermostat dispatcher error."""


class ThermostatDispatcherConfigurationError(ThermostatDispatcherError):
    """Raised for missing or invalid factory data."""


class _DispatchItem(NamedTuple):
    """One thermostat item definition."""

    index: int
    key_candidates: tuple[str, ...]
    required: bool
    kind: str
    description: str


class ThermostatDispatcher(ProvisionDispatcher):
    """Dispatcher for thermostat provisioning format."""

    _READ_TIMEOUT_SEC = 0.1
    _SPAKE2P_W0_SIZE = 32
    _SPAKE2P_L_SIZE = 65
    _SPAKE2P_VERIFIER_SIZE = _SPAKE2P_W0_SIZE + _SPAKE2P_L_SIZE

    _COMMAND_PREFIX = b"se "
    _COMMAND_SUFFIX = b"\x0a"

    _ITEMS: tuple[_DispatchItem, ...] = (
        _DispatchItem(
            index=0,
            key_candidates=("cd_cert", "cd", "certification_declaration"),
            required=True,
            kind="binary_bytes",
            description="Certification Declaration",
        ),
        _DispatchItem(
            index=1,
            key_candidates=("pai_cert", "pai_certificate"),
            required=True,
            kind="binary_bytes",
            description="PAI certificate",
        ),
        _DispatchItem(
            index=2,
            key_candidates=("dac_cert", "dac_certificate"),
            required=True,
            kind="binary_bytes",
            description="DAC certificate",
        ),
        _DispatchItem(
            index=3,
            key_candidates=("dac_private_key", "dac_priv", "dac_key"),
            required=True,
            kind="binary_bytes",
            description="DAC private key",
        ),
        _DispatchItem(
            index=4,
            key_candidates=("dac_public_key", "dac_pub"),
            required=True,
            kind="binary_bytes",
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
            kind="binary_bytes",
            description="SPAKE2+ salt",
        ),
        _DispatchItem(
            index=8,
            key_candidates=("spake2p_verifier_w0", "verifier_w0"),
            required=True,
            kind="binary_bytes",
            description="SPAKE2+ verifier W0",
        ),
        _DispatchItem(
            index=9,
            key_candidates=("spake2p_verifier_L", "verifier_l"),
            required=True,
            kind="binary_bytes",
            description="SPAKE2+ verifier L",
        ),
    )

    def __init__(
        self,
        stream: Stream,
    ) -> None:
        """Initialize dispatcher with transport stream."""
        super().__init__(stream=stream)
        self.stream.subscribe_event(self._on_stream_event)

        self._stop_event = threading.Event()
        self._rx_lock = threading.Lock()
        self._rx_buffer = bytearray()

        self._reader_thread = threading.Thread(
            target=self._reader_loop,
            name="ThermostatDispatcherReader",
            daemon=True,
        )
        self._reader_thread.start()

    def destroy(self) -> None:
        """Release subscriptions and stop reader thread."""
        self._stop_event.set()
        self.stream.unsubscribe_event(self._on_stream_event)

        if self._reader_thread.is_alive():
            self._reader_thread.join(timeout=1.0)

    def is_ready(self) -> bool:
        """Return True when stream is connected."""
        return self.stream.is_connected()

    def dispatch(self, factory_data: dict[str, Any]) -> bool:
        """Send one factory-data payload."""
        if not isinstance(factory_data, dict):
            raise ThermostatDispatcherConfigurationError(
                "The factory data payload must be a dictionary."
            )

        if not self.is_ready():
            return False

        payload_source = dict(factory_data)
        self._expand_combined_verifier(payload_source)

        encoded_records: list[tuple[_DispatchItem, bytes]] = []
        skipped_optional: list[str] = []

        for item in self._ITEMS:
            raw_value = self._find_value(payload_source, item.key_candidates)

            if raw_value is None:
                if item.required:
                    return False

                skipped_optional.append(item.description)
                continue

            payload = self._encode_value(item, raw_value)
            record = self._build_record(item.index, payload)
            encoded_records.append((item, record))

        sent_indices: list[int] = []

        for item, record in encoded_records:
            frame = self._build_command_frame(record)
            self._log_raw_bytes("TX", frame)

            if not self.stream.write(frame):
                return False

            sent_indices.append(item.index)

            Logger.write(
                LogLevel.DEBUG,
                f"Thermostat dispatch sent: idx={item.index}, "
                f"payload_len={len(record) - 3}, "
                f"frame_len={len(frame)}",
            )

        return True

    def _on_stream_event(self, event: StreamEvent) -> None:
        """Handle stream connection events."""
        Logger.write(LogLevel.DEBUG, f"Thermostat stream event: {event.name}")

    def _find_value(
        self,
        factory_data: dict[str, Any],
        keys: tuple[str, ...],
    ) -> Any | None:
        """Return first matching value for candidate keys."""
        for key in keys:
            if key in factory_data:
                return factory_data[key]
        return None

    def _expand_combined_verifier(self, payload_source: dict[str, Any]) -> None:
        """Derive split SPAKE2+ verifier fields from legacy combined value."""
        has_w0 = (
            self._find_value(
                payload_source,
                ("spake2p_verifier_w0", "verifier_w0"),
            )
            is not None
        )
        has_l = (
            self._find_value(
                payload_source,
                ("spake2p_verifier_L", "verifier_l"),
            )
            is not None
        )
        if has_w0 and has_l:
            return

        combined = self._find_value(payload_source, ("spake2p_verifier", "verifier"))
        if combined is None:
            raise ThermostatDispatcherConfigurationError(
                "Required thermostat factory data is missing: SPAKE2+ verifier."
            )

        verifier = self._decode_binary_bytes(combined, "SPAKE2+ verifier")

        if len(verifier) != self._SPAKE2P_VERIFIER_SIZE:
            raise ThermostatDispatcherConfigurationError(
                "The value for 'SPAKE2+ verifier' has an unexpected length."
            )

        w0 = verifier[: self._SPAKE2P_W0_SIZE]
        l_value = verifier[self._SPAKE2P_W0_SIZE :]

        payload_source["spake2p_verifier_w0"] = w0.hex().upper()
        payload_source["spake2p_verifier_L"] = l_value.hex().upper()

    def _encode_value(self, item: _DispatchItem, value: Any) -> bytes:
        """Encode one thermostat item payload."""
        if item.kind == "binary_bytes":
            return self._decode_binary_bytes(value, item.description)

        if item.kind == "u32":
            return self._encode_u32(value, item.description)

        raise ThermostatDispatcherConfigurationError(
            f"Unsupported thermostat item encoding kind: {item.kind}"
        )

    def _decode_binary_bytes(self, value: Any, field_name: str) -> bytes:
        """Decode bytes-like data or encoded string to bytes."""
        if isinstance(value, bytes):
            return value

        if isinstance(value, bytearray):
            return bytes(value)

        if isinstance(value, memoryview):
            return bytes(value)

        if isinstance(value, list):
            try:
                return bytes(value)
            except Exception as exc:
                raise ThermostatDispatcherConfigurationError(
                    f"The value for '{field_name}' is not a valid byte array."
                ) from exc

        if isinstance(value, str):
            normalized = "".join(value.strip().split())

            try:
                return bytes.fromhex(normalized)
            except Exception:
                pass

            try:
                import base64

                return base64.b64decode(normalized, validate=True)
            except Exception as exc:
                raise ThermostatDispatcherConfigurationError(
                    f"The value for '{field_name}' is neither valid hex nor base64."
                ) from exc

        raise ThermostatDispatcherConfigurationError(
            f"The value for '{field_name}' must be bytes-like, byte-array, "
            "or encoded string."
        )

    def _encode_u32(self, value: Any, field_name: str) -> bytes:
        """Encode unsigned 32-bit integer as little-endian bytes."""
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
        """Build one thermostat transfer record."""
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
        """Build final wire frame."""
        return self._COMMAND_PREFIX + record + self._COMMAND_SUFFIX

    def _reader_loop(self) -> None:
        """Read stream chunks and log complete lines."""
        while not self._stop_event.is_set():
            try:
                chunk = self.stream.read(size=1024, timeout=self._READ_TIMEOUT_SEC)
            except Exception as exc:
                Logger.write(
                    LogLevel.WARNING,
                    f"Thermostat dispatcher read failed: {type(exc).__name__}: {exc}",
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
        """Log raw payload in hexadecimal form."""
        Logger.write(
            LogLevel.DEBUG,
            f"Thermostat raw {direction}: len={len(payload)} hex={payload.hex()}",
        )

    def _handle_rx_chunk(self, chunk: bytes) -> None:
        """Append RX chunk and log complete newline-terminated lines."""
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
            Logger.write(LogLevel.DEBUG, text)

    def _decode_rx_line(self, line: bytes) -> str:
        """Decode one RX line; escape invalid UTF-8 bytes."""
        try:
            return line.decode("utf-8")
        except UnicodeDecodeError:
            return line.decode("utf-8", errors="backslashreplace")
