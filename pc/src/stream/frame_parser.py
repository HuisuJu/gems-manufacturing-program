"""Factory frame parser/codec for serial stream transport.

Internal module for stream framing:
- magic sync: 0xFA 0xC0
- header: magic(2, big-endian bytes) + type(1) + size(2, big-endian) + crc16(2, big-endian)
- payload CRC16-CCITT over frame data area
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

FRAME_MAGIC = 0xFAC0
FRAME_MAGIC_BYTES = b"\xFA\xC0"
FRAME_HEADER_SIZE = 7
FRAME_MAX_SIZE = 512
FRAME_MAX_DATA_SIZE = FRAME_MAX_SIZE - FRAME_HEADER_SIZE

FRAME_TYPE_SINGLE = 0x01
FRAME_TYPE_FIRST = 0x02
FRAME_TYPE_CONSECUTIVE = 0x03
FRAME_TYPE_ACK = 0xF1
FRAME_TYPE_NACK = 0xF2

MAX_RETRY_COUNT = 3
FLOW_CONTROL_TIMEOUT_SEC = 0.5


@dataclass(slots=True)
class DecodedFrame:
    frame_type: int
    size: int
    crc16: int
    payload: bytes


def crc16_ccitt(data: bytes) -> int:
    crc = 0xFFFF
    for byte in data:
        crc ^= (byte << 8)
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ 0x1021) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    return crc


def _u16be(value: int) -> bytes:
    return value.to_bytes(2, byteorder="big", signed=False)


def _read_u16be(buf: bytes) -> int:
    return int.from_bytes(buf, byteorder="big", signed=False)


def _u32be(value: int) -> bytes:
    return value.to_bytes(4, byteorder="big", signed=False)


def _read_u32be(buf: bytes) -> int:
    return int.from_bytes(buf, byteorder="big", signed=False)


def encode_frame(frame_type: int, payload: bytes) -> bytes:
    size = len(payload)
    if size > FRAME_MAX_DATA_SIZE:
        raise ValueError("frame payload too large")

    crc = crc16_ccitt(payload)
    return FRAME_MAGIC_BYTES + bytes([frame_type]) + _u16be(size) + _u16be(crc) + payload


def decode_frame(raw: bytes) -> DecodedFrame:
    if len(raw) < FRAME_HEADER_SIZE:
        raise ValueError("frame too short")
    if raw[0:2] != FRAME_MAGIC_BYTES:
        raise ValueError("invalid frame magic")

    frame_type = raw[2]
    size = _read_u16be(raw[3:5])
    crc16 = _read_u16be(raw[5:7])
    if len(raw) != FRAME_HEADER_SIZE + size:
        raise ValueError("frame size mismatch")

    payload = raw[7:]
    if crc16_ccitt(payload) != crc16:
        raise ValueError("crc mismatch")

    return DecodedFrame(frame_type=frame_type, size=size, crc16=crc16, payload=payload)


def control_sequence_from_frame(frame: DecodedFrame) -> int:
    if frame.frame_type not in (FRAME_TYPE_ACK, FRAME_TYPE_NACK):
        raise ValueError("not a control frame")
    if frame.size != 1:
        raise ValueError("invalid control frame payload size")
    return frame.payload[0]


def build_control_frame(is_ack: bool, sequence: int) -> bytes:
    if not (0 <= sequence <= 0xFF):
        raise ValueError("sequence out of range")
    return encode_frame(FRAME_TYPE_ACK if is_ack else FRAME_TYPE_NACK, bytes([sequence]))


def frame_sequence(frame: DecodedFrame) -> Optional[int]:
    if frame.frame_type == FRAME_TYPE_SINGLE:
        return 0xFF
    if frame.frame_type == FRAME_TYPE_FIRST:
        if len(frame.payload) < 5:
            return None
        return frame.payload[4]
    if frame.frame_type == FRAME_TYPE_CONSECUTIVE:
        if len(frame.payload) < 1:
            return None
        return frame.payload[0]
    if frame.frame_type in (FRAME_TYPE_ACK, FRAME_TYPE_NACK):
        if len(frame.payload) != 1:
            return None
        return frame.payload[0]
    return None


class StreamFrameParser:
    """Incremental byte-stream parser for factory frames."""

    def __init__(self) -> None:
        self._buffer = bytearray()

    def feed(self, data: bytes) -> list[DecodedFrame]:
        if not data:
            return []

        self._buffer.extend(data)
        out: list[DecodedFrame] = []

        while True:
            if len(self._buffer) < FRAME_HEADER_SIZE:
                break

            idx = self._buffer.find(FRAME_MAGIC_BYTES)
            if idx < 0:
                self._buffer.clear()
                break
            if idx > 0:
                del self._buffer[:idx]

            if len(self._buffer) < FRAME_HEADER_SIZE:
                break

            size = _read_u16be(self._buffer[3:5])
            total = FRAME_HEADER_SIZE + size
            if size > FRAME_MAX_DATA_SIZE:
                del self._buffer[:2]
                continue
            if len(self._buffer) < total:
                break

            raw = bytes(self._buffer[:total])
            del self._buffer[:total]

            try:
                out.append(decode_frame(raw))
            except ValueError:
                continue

        return out


class PacketFragmenter:
    """Fragment one logical packet into factory frames."""

    def __init__(self, packet: bytes):
        if not packet:
            raise ValueError("packet must not be empty")
        self._packet = packet
        self._size = len(packet)
        self._index = 0
        self._sequence = 0
        self._need_fragmentation = self._size > FRAME_MAX_DATA_SIZE

    def done(self) -> bool:
        return self._index >= self._size

    def next_frame(self) -> tuple[bytes, int]:
        if self.done():
            raise StopIteration

        if not self._need_fragmentation:
            payload = self._packet
            self._index = self._size
            return encode_frame(FRAME_TYPE_SINGLE, payload), 0xFF

        if self._sequence == 0:
            first_data_max = FRAME_MAX_DATA_SIZE - 4 - 1
            chunk = self._packet[:first_data_max]
            payload = _u32be(self._size) + bytes([0]) + chunk
            self._index = len(chunk)
            self._sequence = 1
            return encode_frame(FRAME_TYPE_FIRST, payload), 0

        cons_data_max = FRAME_MAX_DATA_SIZE - 1
        remaining = self._size - self._index
        take = min(cons_data_max, remaining)
        chunk = self._packet[self._index:self._index + take]
        seq = self._sequence & 0xFF
        payload = bytes([seq]) + chunk
        self._index += take
        self._sequence += 1
        return encode_frame(FRAME_TYPE_CONSECUTIVE, payload), seq


class PacketAssembler:
    """Reassemble factory data frames into one logical packet."""

    def __init__(self):
        self.last_accepted_sequence: Optional[int] = None
        self.last_accepted_type: Optional[int] = None
        self.reset()

    def reset(self) -> None:
        self.expected_sequence = 0
        self.total_size = 0
        self.buffer = bytearray()

    def _mark_accepted(self, frame_type: int, seq: int) -> None:
        self.last_accepted_type = frame_type
        self.last_accepted_sequence = seq

    def process(self, frame: DecodedFrame) -> tuple[str, Optional[bytes], Optional[int]]:
        """Process one frame.

        Returns:
            ("ignore", None, None)
            ("duplicate", None, seq)
            ("ok", None, seq)
            ("done", packet, seq)
            ("error", None, seq)
        """
        seq = frame_sequence(frame)
        if seq is None:
            return "error", None, None

        if frame.frame_type == FRAME_TYPE_SINGLE:
            self._mark_accepted(FRAME_TYPE_SINGLE, 0xFF)
            self.reset()
            return "done", frame.payload, 0xFF

        if frame.frame_type == FRAME_TYPE_FIRST:
            if len(frame.payload) < 5 or frame.payload[4] != 0:
                self.reset()
                return "error", None, seq
            total_size = _read_u32be(frame.payload[0:4])
            chunk = frame.payload[5:]
            if total_size < len(chunk):
                self.reset()
                return "error", None, seq

            self.total_size = total_size
            self.buffer = bytearray(chunk)
            self.expected_sequence = 1
            self._mark_accepted(FRAME_TYPE_FIRST, seq)
            if len(self.buffer) >= self.total_size:
                packet = bytes(self.buffer[:self.total_size])
                self.reset()
                return "done", packet, seq
            return "ok", None, seq

        if frame.frame_type == FRAME_TYPE_CONSECUTIVE:
            if self.total_size == 0:
                if self.last_accepted_type in (FRAME_TYPE_FIRST, FRAME_TYPE_CONSECUTIVE) and self.last_accepted_sequence == seq:
                    return "duplicate", None, seq
                self.reset()
                return "error", None, seq
            if seq < self.expected_sequence:
                return "duplicate", None, seq
            if seq != self.expected_sequence:
                self.reset()
                return "error", None, seq

            self.buffer.extend(frame.payload[1:])
            self.expected_sequence += 1
            self._mark_accepted(FRAME_TYPE_CONSECUTIVE, seq)
            if len(self.buffer) >= self.total_size:
                packet = bytes(self.buffer[:self.total_size])
                self.reset()
                return "done", packet, seq
            return "ok", None, seq

        return "ignore", None, None
