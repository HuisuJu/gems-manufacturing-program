# packet_builders.py
from __future__ import annotations

from dataclasses import dataclass

from .packet import PacketType, PacketBuilder


@dataclass(slots=True)
class PcAdvBuilder(PacketBuilder):
    version: int = 1

    def __init__(self, version: int = 1):
        super().__init__(type=PacketType.PC_ADV, payload=b"", session_id=0)
        self.version = int(version) & 0xFF
        self.payload = bytes([self.version])


@dataclass(slots=True)
class PcHelloBuilder(PacketBuilder):
    version: int = 1

    def __init__(self, version: int = 1):
        super().__init__(type=PacketType.PC_HELLO, payload=b"", session_id=0)
        self.version = int(version) & 0xFF
        self.payload = bytes([self.version])


@dataclass(slots=True)
class PcAlertBuilder(PacketBuilder):
    reason: bytes = b""

    def __init__(self, reason: bytes = b""):
        super().__init__(type=PacketType.PC_ALERT, payload=b"", session_id=0)
        self.reason = bytes(reason)
        self.payload = self.reason


@dataclass(slots=True)
class PcFinishBuilder(PacketBuilder):
    data: bytes = b""

    def __init__(self, session_id: int, data: bytes = b""):
        super().__init__(type=PacketType.PC_FINISH, payload=b"", session_id=int(session_id))
        self.data = bytes(data)
        self.payload = self.data


@dataclass(slots=True)
class InformationBuilder(PacketBuilder):
    data: bytes = b""

    def __init__(self, session_id: int, data: bytes):
        super().__init__(type=PacketType.INFORMATION, payload=b"", session_id=int(session_id))
        self.data = bytes(data)
        self.payload = self.data