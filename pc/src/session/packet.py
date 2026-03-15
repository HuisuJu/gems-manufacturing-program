from __future__ import annotations

from dataclasses import dataclass

from frame.protocol import decode_u32_be, encode_u32_be

from .protocol import (
    PROTOCOL_VERSION,
    SESSION_HEADER_SIZE,
    SESSION_ID_SIZE,
    SESSIONLESS_HEADER_SIZE,
    PacketType,
    SessionArgumentError,
    SessionProtocolError,
    header_size_for,
    is_sessionless_packet,
)


@dataclass(slots=True)
class SessionPacket:
    """Concrete session-layer packet."""

    type: PacketType
    payload: bytes
    flag: int = 0
    session_id: bytes | None = None

    def __post_init__(self) -> None:
        self.payload = bytes(self.payload)
        self.flag &= 0xFF

        if is_sessionless_packet(self.type):
            if self.session_id not in (None, b""):
                raise SessionArgumentError("sessionless packet must not carry a session_id.")
            self.session_id = None
        else:
            if self.session_id is None:
                raise SessionArgumentError("session packet requires a 16-byte session_id.")

            self.session_id = bytes(self.session_id)
            if len(self.session_id) != SESSION_ID_SIZE:
                raise SessionArgumentError("session packet session_id must be exactly 16 bytes.")

    @property
    def version(self) -> int:
        """Return the protocol version."""
        return PROTOCOL_VERSION

    @property
    def is_sessionless(self) -> bool:
        """Return whether this packet uses the sessionless header."""
        return is_sessionless_packet(self.type)

    @property
    def header_size(self) -> int:
        """Return the encoded header size for this packet."""
        return header_size_for(self.type)

    @property
    def encoded_size(self) -> int:
        """Return the total encoded packet size."""
        return self.header_size + len(self.payload)

    def encode(self) -> bytes:
        """Encode the packet into wire-format bytes."""
        prefix = bytes((self.version, int(self.type), self.flag))

        if self.is_sessionless:
            return prefix + encode_u32_be(len(self.payload)) + self.payload

        assert self.session_id is not None
        return prefix + self.session_id + encode_u32_be(len(self.payload)) + self.payload

    @classmethod
    def decode(cls, raw: bytes) -> "SessionPacket":
        """Decode a complete wire-format session packet."""
        raw = bytes(raw)

        if len(raw) < SESSIONLESS_HEADER_SIZE:
            raise SessionProtocolError("session packet is shorter than the minimum header size.")

        version = raw[0]
        if version != PROTOCOL_VERSION:
            raise SessionProtocolError("session packet version mismatch.")

        try:
            packet_type = PacketType(raw[1])
        except ValueError as exc:
            raise SessionProtocolError(f"unsupported session packet type: {raw[1]!r}") from exc

        flag = raw[2]
        sessionless = is_sessionless_packet(packet_type)

        if sessionless:
            if len(raw) < SESSIONLESS_HEADER_SIZE:
                raise SessionProtocolError("sessionless packet is shorter than its header.")
            payload_size = decode_u32_be(raw[3:7])
            expected_size = SESSIONLESS_HEADER_SIZE + payload_size

            if len(raw) != expected_size:
                raise SessionProtocolError("sessionless packet size mismatch.")

            payload = raw[SESSIONLESS_HEADER_SIZE:]
            return cls(
                type=packet_type,
                flag=flag,
                payload=payload,
                session_id=None,
            )

        if len(raw) < SESSION_HEADER_SIZE:
            raise SessionProtocolError("session packet is shorter than its header.")

        session_id = raw[3 : 3 + SESSION_ID_SIZE]
        payload_size = decode_u32_be(raw[3 + SESSION_ID_SIZE : 3 + SESSION_ID_SIZE + 4])
        expected_size = SESSION_HEADER_SIZE + payload_size

        if len(raw) != expected_size:
            raise SessionProtocolError("session packet size mismatch.")

        payload = raw[SESSION_HEADER_SIZE:]
        return cls(
            type=packet_type,
            flag=flag,
            payload=payload,
            session_id=session_id,
        )
