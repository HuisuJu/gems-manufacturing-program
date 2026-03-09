from __future__ import annotations

from dataclasses import dataclass

from .packet import PacketType, PacketBuilder, SESSION_ID_SIZE


@dataclass(slots=True)
class PcAdvBuilder(PacketBuilder):
    payload_raw: bytes = b""

    def __init__(self, payload_raw: bytes):
        super().__init__(type=PacketType.UNKNOWN, payload=b"", session_id=b"")
        self.payload_raw = bytes(payload_raw)

    def build(self) -> bytes:
        return self.payload_raw


@dataclass(slots=True)
class PcHelloBuilder(PacketBuilder):
    session_id: bytes = b""
    payload_version: int = 1

    def __init__(self, session_id: bytes, payload_version: int = 1):
        super().__init__(type=PacketType.PC_HELLO, payload=b"", session_id=b"")
        session_id = bytes(session_id)
        if len(session_id) != SESSION_ID_SIZE:
            raise ValueError("PC_HELLO session_id must be 16 bytes")

        self.session_id = session_id
        self.payload_version = int(payload_version) & 0xFF
        payload_size = 2 + SESSION_ID_SIZE
        self.payload = bytes([self.payload_version, payload_size]) + session_id


@dataclass(slots=True)
class PcAlertBuilder(PacketBuilder):
    reason: bytes = b""

    def __init__(self, reason: bytes = b""):
        super().__init__(type=PacketType.PC_ALERT, payload=b"", session_id=b"")
        self.reason = bytes(reason)
        self.payload = self.reason


@dataclass(slots=True)
class PcFinishBuilder(PacketBuilder):
    data: bytes = b""

    def __init__(self, session_id: bytes, data: bytes = b""):
        super().__init__(type=PacketType.PC_BYE, payload=b"", session_id=session_id)
        self.data = bytes(data)
        self.payload = self.data


@dataclass(slots=True)
class InformationBuilder(PacketBuilder):
    data: bytes = b""

    def __init__(self, session_id: bytes, data: bytes):
        super().__init__(type=PacketType.MESSAGE, payload=b"", session_id=session_id)
        self.data = bytes(data)
        self.payload = self.data