from __future__ import annotations

from enum import IntEnum


FRAME_MAGIC = 0xFAC0
FRAME_MAX_SIZE = 512
FRAME_HEADER_SIZE = 7
FRAME_MAX_DATA_SIZE = FRAME_MAX_SIZE - FRAME_HEADER_SIZE

FRAME_FIRST_METADATA_SIZE = 4 + 1  # total_size(4) + sequence(1)
FRAME_CONSECUTIVE_METADATA_SIZE = 1
FRAME_CONTROL_PAYLOAD_SIZE = 1

FRAME_SINGLE_SEQUENCE = 0xFF

DEFAULT_FLOW_CONTROL_TIMEOUT = 0.5
DEFAULT_READ_TIMEOUT = 1.0
DEFAULT_WRITE_TIMEOUT = 1.0
DEFAULT_RETRY_COUNT = 3


class FrameType(IntEnum):
    SINGLE = 0x01
    FIRST = 0x02
    CONSECUTIVE = 0x03
    ACK = 0xF1
    NACK = 0xF2


class FrameError(Exception):
    """Base exception for frame-layer failures."""


class FrameArgumentError(FrameError):
    """Raised when a frame API receives an invalid argument."""


class FrameMagicError(FrameError):
    """Raised when the frame magic number does not match."""


class FrameCrcError(FrameError):
    """Raised when the frame CRC check fails."""


class FrameSequenceError(FrameError):
    """Raised when the frame sequence is invalid or unexpected."""


class FrameOverflowError(FrameError):
    """Raised when a frame or packet exceeds configured limits."""


class FrameTimeoutError(FrameError):
    """Raised when waiting for frame data times out."""


class FrameIOError(FrameError):
    """Raised when the underlying stream I/O fails."""


def encode_u16_be(value: int) -> bytes:
    """Encode a 16-bit unsigned integer to big-endian bytes."""
    if value < 0 or value > 0xFFFF:
        raise FrameArgumentError("u16 value out of range.")
    return value.to_bytes(2, byteorder="big", signed=False)


def encode_u32_be(value: int) -> bytes:
    """Encode a 32-bit unsigned integer to big-endian bytes."""
    if value < 0 or value > 0xFFFFFFFF:
        raise FrameArgumentError("u32 value out of range.")
    return value.to_bytes(4, byteorder="big", signed=False)


def decode_u16_be(data: bytes) -> int:
    """Decode a 16-bit unsigned integer from big-endian bytes."""
    if len(data) != 2:
        raise FrameArgumentError("u16 decode requires exactly 2 bytes.")
    return int.from_bytes(data, byteorder="big", signed=False)


def decode_u32_be(data: bytes) -> int:
    """Decode a 32-bit unsigned integer from big-endian bytes."""
    if len(data) != 4:
        raise FrameArgumentError("u32 decode requires exactly 4 bytes.")
    return int.from_bytes(data, byteorder="big", signed=False)


def crc16_ccitt(data: bytes) -> int:
    """Compute CRC-16-CCITT using poly 0x1021 and init 0xFFFF."""
    crc = 0xFFFF

    for byte in data:
        crc ^= (byte << 8)

        for _ in range(8):
            if (crc & 0x8000) != 0:
                crc = ((crc << 1) ^ 0x1021) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF

    return crc


def is_control_frame_type(frame_type: FrameType) -> bool:
    """Return whether the frame type is ACK or NACK."""
    return frame_type in (FrameType.ACK, FrameType.NACK)


def max_first_frame_data_size() -> int:
    """Return the maximum user-data size carried by a FIRST frame."""
    return FRAME_MAX_DATA_SIZE - FRAME_FIRST_METADATA_SIZE


def max_consecutive_frame_data_size() -> int:
    """Return the maximum user-data size carried by a CONSECUTIVE frame."""
    return FRAME_MAX_DATA_SIZE - FRAME_CONSECUTIVE_METADATA_SIZE
