from __future__ import annotations

from dataclasses import dataclass

from .packet import PacketType, PacketParser


@dataclass(slots=True)
class DevHelloParser(PacketParser):
    device_uuid: int = 0
    require_auth: bool = False

    def __init__(self):
        super().__init__()
        self.device_uuid = 0
        self.require_auth = False

    def parse(self, packet: bytes) -> None:
        super().parse(packet)
        if self.type != PacketType.DEV_HELLO:
            raise ValueError(f"unexpected packet type: {self.type.name}")
        if len(self.payload) < 11:
            raise ValueError("DEV_HELLO payload too short")

        payload_version = self.payload[0]
        payload_size = self.payload[1]
        if payload_version != 0x01:
            raise ValueError("DEV_HELLO payload version mismatch")
        if payload_size > len(self.payload) or payload_size < 11:
            raise ValueError("DEV_HELLO payload size invalid")

        self.device_uuid = int.from_bytes(self.payload[2:10], byteorder="big", signed=False)
        self.require_auth = self.payload[10] != 0


@dataclass(slots=True)
class DevAlertParser(PacketParser):
    reason: bytes = b""

    def __init__(self):
        super().__init__()
        self.reason = b""

    def parse(self, packet: bytes) -> None:
        super().parse(packet)
        if self.type != PacketType.DEV_ALERT:
            raise ValueError(f"unexpected packet type: {self.type.name}")
        self.reason = self.payload


@dataclass(slots=True)
class InformationParser(PacketParser):
    data: bytes = b""

    def __init__(self):
        super().__init__()
        self.data = b""

    def parse(self, packet: bytes) -> None:
        super().parse(packet)
        if self.type != PacketType.MESSAGE:
            raise ValueError(f"unexpected packet type: {self.type.name}")
        if len(self.session_id) != 16:
            raise ValueError("MESSAGE invalid session_id length")
        self.data = self.payload
