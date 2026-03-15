from __future__ import annotations

from dataclasses import dataclass

from .protocol import (
    FRAME_CONTROL_PAYLOAD_SIZE,
    FRAME_HEADER_SIZE,
    FRAME_MAGIC,
    FRAME_SINGLE_SEQUENCE,
    FRAME_MAX_DATA_SIZE,
    FrameArgumentError,
    FrameCrcError,
    FrameMagicError,
    FrameType,
    crc16_ccitt,
    decode_u16_be,
    encode_u16_be,
    is_control_frame_type,
)


@dataclass(slots=True)
class Frame:
    """Concrete frame object for the factory framing protocol."""

    type: FrameType
    payload: bytes

    def __post_init__(self) -> None:
        self.payload = bytes(self.payload)

        if len(self.payload) > FRAME_MAX_DATA_SIZE:
            raise FrameArgumentError("frame payload exceeds maximum frame data size.")

    @property
    def magic(self) -> int:
        """Return the frame magic value."""
        return FRAME_MAGIC

    @property
    def size(self) -> int:
        """Return the payload size."""
        return len(self.payload)

    @property
    def crc16(self) -> int:
        """Return the CRC16 over the payload."""
        return crc16_ccitt(self.payload)

    def encode(self) -> bytes:
        """Encode the frame into wire-format bytes."""
        header = b"".join(
            (
                encode_u16_be(FRAME_MAGIC),
                bytes((int(self.type),)),
                encode_u16_be(self.size),
                encode_u16_be(self.crc16),
            )
        )
        return header + self.payload

    def sequence(self) -> int:
        """
        Return the logical sequence number of this frame.

        SINGLE returns 0xFF.
        FIRST / CONSECUTIVE / ACK / NACK return the sequence byte.
        """
        if self.type == FrameType.SINGLE:
            return FRAME_SINGLE_SEQUENCE

        if self.type in (
            FrameType.FIRST,
            FrameType.CONSECUTIVE,
            FrameType.ACK,
            FrameType.NACK,
        ):
            if len(self.payload) < 1:
                raise FrameArgumentError("frame payload does not contain a sequence byte.")

            if self.type == FrameType.FIRST:
                if len(self.payload) < 5:
                    raise FrameArgumentError("FIRST frame payload is too short.")
                return self.payload[4]

            return self.payload[0]

        raise FrameArgumentError(f"unsupported frame type: {self.type!r}")

    def is_ack(self) -> bool:
        """Return whether this is an ACK control frame."""
        return self.type == FrameType.ACK

    def is_nack(self) -> bool:
        """Return whether this is a NACK control frame."""
        return self.type == FrameType.NACK

    def is_control(self) -> bool:
        """Return whether this is a control frame."""
        return is_control_frame_type(self.type)

    @classmethod
    def decode(cls, raw: bytes) -> "Frame":
        """Decode and validate one complete wire-format frame."""
        raw = bytes(raw)

        if len(raw) < FRAME_HEADER_SIZE:
            raise FrameArgumentError("raw frame is shorter than frame header size.")

        magic = decode_u16_be(raw[0:2])
        if magic != FRAME_MAGIC:
            raise FrameMagicError("frame magic number mismatch.")

        try:
            frame_type = FrameType(raw[2])
        except ValueError as exc:
            raise FrameArgumentError(f"unsupported frame type value: {raw[2]!r}") from exc

        payload_size = decode_u16_be(raw[3:5])
        crc16 = decode_u16_be(raw[5:7])

        if payload_size > FRAME_MAX_DATA_SIZE:
            raise FrameArgumentError("frame payload size exceeds maximum frame data size.")

        expected_size = FRAME_HEADER_SIZE + payload_size
        if len(raw) != expected_size:
            raise FrameArgumentError("raw frame length does not match encoded payload size.")

        payload = raw[FRAME_HEADER_SIZE:]
        calculated_crc = crc16_ccitt(payload)
        if calculated_crc != crc16:
            raise FrameCrcError("frame CRC mismatch.")

        return cls(type=frame_type, payload=payload)

    @classmethod
    def build_single(cls, data: bytes) -> "Frame":
        """Build a SINGLE frame containing the complete packet."""
        return cls(type=FrameType.SINGLE, payload=bytes(data))

    @classmethod
    def build_first(cls, total_size: int, sequence: int, chunk: bytes) -> "Frame":
        """Build a FIRST frame for a fragmented packet."""
        if total_size < 0 or total_size > 0xFFFFFFFF:
            raise FrameArgumentError("total_size is out of range for FIRST frame.")

        if sequence != 0:
            raise FrameArgumentError("FIRST frame sequence must be 0.")

        payload = total_size.to_bytes(4, byteorder="big", signed=False) + bytes((sequence,)) + bytes(chunk)
        return cls(type=FrameType.FIRST, payload=payload)

    @classmethod
    def build_consecutive(cls, sequence: int, chunk: bytes) -> "Frame":
        """Build a CONSECUTIVE frame."""
        if sequence < 0 or sequence > 0xFF:
            raise FrameArgumentError("consecutive sequence is out of range.")

        payload = bytes((sequence,)) + bytes(chunk)
        return cls(type=FrameType.CONSECUTIVE, payload=payload)

    @classmethod
    def build_ack(cls, sequence: int) -> "Frame":
        """Build an ACK control frame."""
        return cls._build_control(FrameType.ACK, sequence)

    @classmethod
    def build_nack(cls, sequence: int) -> "Frame":
        """Build a NACK control frame."""
        return cls._build_control(FrameType.NACK, sequence)

    @classmethod
    def _build_control(cls, frame_type: FrameType, sequence: int) -> "Frame":
        """Build one control frame."""
        if frame_type not in (FrameType.ACK, FrameType.NACK):
            raise FrameArgumentError("control frame type must be ACK or NACK.")

        if sequence < 0 or sequence > 0xFF:
            raise FrameArgumentError("control frame sequence is out of range.")

        payload = bytes((sequence,))
        if len(payload) != FRAME_CONTROL_PAYLOAD_SIZE:
            raise FrameArgumentError("invalid control payload size.")

        return cls(type=frame_type, payload=payload)