# packet.py
from __future__ import annotations

from enum import IntEnum
import zlib


class PacketType(IntEnum):
    PC_ADV = 0x01
    PC_HELLO = 0x02
    PC_ALERT = 0x03
    PC_FINISH = 0x04

    DEV_HELLO = 0x11
    DEV_ALERT = 0x12

    INFORMATION = 0x20
    UNKNOWN = 0xFF


MAGIC = 0xFAC0
MAGIC_BYTES = MAGIC.to_bytes(2, "big")


_SESSIONLESS_TYPES = {
    PacketType.PC_ADV,
    PacketType.PC_HELLO,
    PacketType.PC_ALERT,
    PacketType.DEV_HELLO,
    PacketType.DEV_ALERT,
}


def _is_sessionless(type: PacketType) -> bool:
    return type in _SESSIONLESS_TYPES


def _u16_to_bytes(x: int) -> bytes:
    return (x & 0xFFFF).to_bytes(2, "big")


def _bytes_to_u16(b: bytes) -> int:
    return int.from_bytes(b, "big")


def _u32_to_bytes(x: int) -> bytes:
    return (x & 0xFFFFFFFF).to_bytes(4, "big")


def _bytes_to_u32(b: bytes) -> int:
    return int.from_bytes(b, "big")


def _crc32(data: bytes) -> int:
    return zlib.crc32(data) & 0xFFFFFFFF


class PacketBuilder:
    def __init__(
        self,
        type: PacketType = PacketType.UNKNOWN,
        payload: bytes = b"",
        session_id: int = 0,
    ):
        self.type: PacketType = type
        self.session_id: int = session_id
        self.payload: bytes = payload

    def build(self) -> bytes:
        if not isinstance(self.payload, (bytes, bytearray, memoryview)):
            raise TypeError("payload must be bytes-like")

        payload = bytes(self.payload)
        if len(payload) > 0xFFFF:
            raise ValueError("payload too large (max 65535)")

        if _is_sessionless(self.type):
            body = (
                MAGIC_BYTES
                + bytes([int(self.type) & 0xFF])
                + _u16_to_bytes(len(payload))
                + payload
            )
        else:
            if not (1 <= self.session_id <= 0xFFFF):
                raise ValueError("session_id must be 1..65535 for session packets")

            body = (
                MAGIC_BYTES
                + bytes([int(self.type) & 0xFF])
                + _u16_to_bytes(self.session_id)
                + _u16_to_bytes(len(payload))
                + payload
            )

        return body + _u32_to_bytes(_crc32(body))


class PacketParser:
    def __init__(self):
        self.type: PacketType = PacketType.UNKNOWN
        self.session_id: int = 0
        self.payload: bytes = b""

    def parse(self, packet: bytes) -> None:
        if not isinstance(packet, (bytes, bytearray, memoryview)):
            raise TypeError("packet must be bytes-like")

        packet = bytes(packet)

        if len(packet) < 2 + 1 + 2 + 4:
            raise ValueError("packet too short")

        if packet[0:2] != MAGIC_BYTES:
            raise ValueError("bad magic")

        raw_type = packet[2]
        try:
            type = PacketType(raw_type)
        except ValueError:
            type = PacketType.UNKNOWN

        if _is_sessionless(type):
            size = _bytes_to_u16(packet[3:5])
            expected = 2 + 1 + 2 + size + 4
            if len(packet) != expected:
                raise ValueError("size mismatch")

            body = packet[:-4]
            recv_crc = _bytes_to_u32(packet[-4:])
            calc_crc = _crc32(body)
            if recv_crc != calc_crc:
                raise ValueError("crc mismatch")

            self.type = type
            self.session_id = 0
            self.payload = packet[5:-4]
            return

        if len(packet) < 2 + 1 + 2 + 2 + 4:
            raise ValueError("session header too short")

        session_id = _bytes_to_u16(packet[3:5])
        if session_id == 0:
            raise ValueError("invalid session_id=0")

        size = _bytes_to_u16(packet[5:7])
        expected = 2 + 1 + 2 + 2 + size + 4
        if len(packet) != expected:
            raise ValueError("size mismatch")

        body = packet[:-4]
        recv_crc = _bytes_to_u32(packet[-4:])
        calc_crc = _crc32(body)
        if recv_crc != calc_crc:
            raise ValueError("crc mismatch")

        self.type = type
        self.session_id = session_id
        self.payload = packet[7:-4]
