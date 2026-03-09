from __future__ import annotations

from enum import IntEnum


class PacketType(IntEnum):
    MESSAGE = 0x01

    PC_HELLO = 0x10
    PC_BYE = 0x11
    PC_ALERT = 0x12

    DEV_HELLO = 0x20
    DEV_BYE = 0x21
    DEV_ALERT = 0x22
    DEV_CHALLENGE = 0x23

    UNKNOWN = 0xFF


PROTOCOL_VERSION = 0x01
SESSION_ID_SIZE = 16


_SESSIONLESS_TYPES = {
    PacketType.PC_HELLO,
    PacketType.PC_ALERT,
    PacketType.DEV_HELLO,
    PacketType.DEV_ALERT,
    PacketType.DEV_CHALLENGE,
}


def _is_sessionless(type: PacketType) -> bool:
    return type in _SESSIONLESS_TYPES


def _u32_to_bytes(x: int) -> bytes:
    return (x & 0xFFFFFFFF).to_bytes(4, "big")


def _bytes_to_u32(b: bytes) -> int:
    return int.from_bytes(b, "big")


class PacketBuilder:
    def __init__(
        self,
        type: PacketType = PacketType.UNKNOWN,
        payload: bytes = b"",
        session_id: bytes = b"",
        flag: int = 0,
    ):
        self.type: PacketType = type
        self.session_id: bytes = bytes(session_id)
        self.flag: int = int(flag) & 0xFF
        self.payload: bytes = payload

    def build(self) -> bytes:
        if not isinstance(self.payload, (bytes, bytearray, memoryview)):
            raise TypeError("payload must be bytes-like")

        payload = bytes(self.payload)
        if len(payload) > 0xFFFFFFFF:
            raise ValueError("payload too large")

        if _is_sessionless(self.type):
            return (
                bytes([PROTOCOL_VERSION, int(self.type) & 0xFF, self.flag])
                + _u32_to_bytes(len(payload))
                + payload
            )
        else:
            if len(self.session_id) != SESSION_ID_SIZE:
                raise ValueError("session_id must be 16 bytes for session packets")

            return (
                bytes([PROTOCOL_VERSION, int(self.type) & 0xFF, self.flag])
                + self.session_id
                + _u32_to_bytes(len(payload))
                + payload
            )


class PacketParser:
    def __init__(self):
        self.type: PacketType = PacketType.UNKNOWN
        self.session_id: bytes = b""
        self.flag: int = 0
        self.payload: bytes = b""

    def parse(self, packet: bytes) -> None:
        if not isinstance(packet, (bytes, bytearray, memoryview)):
            raise TypeError("packet must be bytes-like")

        packet = bytes(packet)

        if len(packet) < 3 + 4:
            raise ValueError("packet too short")

        if packet[0] != PROTOCOL_VERSION:
            raise ValueError("bad protocol version")

        raw_type = packet[1]
        try:
            type = PacketType(raw_type)
        except ValueError:
            type = PacketType.UNKNOWN
        flag = packet[2]

        if _is_sessionless(type):
            size = _bytes_to_u32(packet[3:7])
            expected = 3 + 4 + size
            if len(packet) != expected:
                raise ValueError("size mismatch")

            self.type = type
            self.flag = flag
            self.session_id = b""
            self.payload = packet[7:]
            return

        if len(packet) < 3 + SESSION_ID_SIZE + 4:
            raise ValueError("session header too short")

        session_id = packet[3:3 + SESSION_ID_SIZE]
        size = _bytes_to_u32(packet[3 + SESSION_ID_SIZE:3 + SESSION_ID_SIZE + 4])
        expected = 3 + SESSION_ID_SIZE + 4 + size
        if len(packet) != expected:
            raise ValueError("size mismatch")

        self.type = type
        self.flag = flag
        self.session_id = session_id
        self.payload = packet[3 + SESSION_ID_SIZE + 4:]
