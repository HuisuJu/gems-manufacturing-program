# packet_parsers.py
from __future__ import annotations

from dataclasses import dataclass

from .packet import PacketType, PacketParser


@dataclass(slots=True)
class DevHelloParser(PacketParser):
    device_id: bytes = b""

    def __init__(self):
        super().__init__()
        self.device_id = b""

    def parse(self, packet: bytes) -> None:
        super().parse(packet)
        if self.type != PacketType.DEV_HELLO:
            raise ValueError(f"unexpected packet type: {self.type.name}")
        if len(self.payload) == 0:
            raise ValueError("DEV_HELLO empty device_id")
        self.device_id = self.payload


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
        if self.type != PacketType.INFORMATION:
            raise ValueError(f"unexpected packet type: {self.type.name}")
        if self.session_id == 0:
            raise ValueError("INFORMATION invalid session_id=0")
        self.data = self.payload
