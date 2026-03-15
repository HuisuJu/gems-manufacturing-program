from __future__ import annotations

import secrets
from dataclasses import dataclass
from enum import IntEnum


PROTOCOL_VERSION = 0x01
SESSION_ID_SIZE = 16

SESSIONLESS_HEADER_SIZE = 7
SESSION_HEADER_SIZE = 3 + SESSION_ID_SIZE + 4

PC_HELLO_PAYLOAD_VERSION = 0x01
PC_HELLO_PAYLOAD_MIN_SIZE = 2 + SESSION_ID_SIZE

DEVICE_HELLO_PAYLOAD_MIN_SIZE = 2  # UUID_SIZE(1) + AUTH_REQUIRED(1)
DEVICE_HELLO_UUID_MAX_SIZE = 0xFF


class SessionError(Exception):
    """Base exception for session-layer failures."""


class SessionArgumentError(SessionError):
    """Raised when a session API receives an invalid argument."""


class SessionProtocolError(SessionError):
    """Raised when a packet or payload violates the session protocol."""


class SessionStateError(SessionError):
    """Raised when a session API is called in the wrong state."""


class SessionOpenError(SessionError):
    """Raised when the session open flow fails."""


class SessionClosedError(SessionError):
    """Raised when the peer closed the session."""


class SessionAlertError(SessionError):
    """Raised when the peer sent an ALERT packet."""

    def __init__(self, reason: bytes = b"") -> None:
        self.reason = bytes(reason)
        super().__init__("peer sent session alert.")


class PacketType(IntEnum):
    MESSAGE = 0x01

    PC_HELLO = 0x10
    PC_BYE = 0x11
    PC_ALERT = 0x12

    DEVICE_HELLO = 0x20
    DEVICE_BYE = 0x21
    DEVICE_ALERT = 0x22
    DEVICE_CHALLENGE = 0x23


@dataclass(slots=True)
class DeviceHelloPayload:
    uuid: bytes
    require_auth: bool


def is_sessionless_packet(packet_type: PacketType) -> bool:
    """Return whether the packet type uses the sessionless header."""
    return packet_type in (
        PacketType.PC_HELLO,
        PacketType.PC_ALERT,
        PacketType.DEVICE_HELLO,
        PacketType.DEVICE_ALERT,
        PacketType.DEVICE_CHALLENGE,
    )


def is_alert_packet(packet_type: PacketType) -> bool:
    """Return whether the packet type is ALERT."""
    return packet_type in (PacketType.PC_ALERT, PacketType.DEVICE_ALERT)


def is_bye_packet(packet_type: PacketType) -> bool:
    """Return whether the packet type is BYE."""
    return packet_type in (PacketType.PC_BYE, PacketType.DEVICE_BYE)


def header_size_for(packet_type: PacketType) -> int:
    """Return the session packet header size for the given type."""
    return SESSIONLESS_HEADER_SIZE if is_sessionless_packet(packet_type) else SESSION_HEADER_SIZE


def generate_session_id() -> bytes:
    """Generate a random 16-byte session identifier."""
    return secrets.token_bytes(SESSION_ID_SIZE)


def build_pc_hello_payload(session_id: bytes) -> bytes:
    """Build the PC_HELLO payload."""
    session_id = bytes(session_id)

    if len(session_id) != SESSION_ID_SIZE:
        raise SessionArgumentError("PC_HELLO session_id must be exactly 16 bytes.")

    payload_size = 2 + SESSION_ID_SIZE
    return bytes((PC_HELLO_PAYLOAD_VERSION, payload_size)) + session_id


def parse_device_hello_payload(payload: bytes) -> DeviceHelloPayload:
    """Parse the DEVICE_HELLO payload."""
    payload = bytes(payload)

    if len(payload) < DEVICE_HELLO_PAYLOAD_MIN_SIZE:
        raise SessionProtocolError("DEVICE_HELLO payload is too short.")

    uuid_size = payload[0]
    expected_size = 1 + uuid_size + 1

    if uuid_size == 0:
        raise SessionProtocolError("DEVICE_HELLO UUID size must not be zero.")

    if uuid_size > DEVICE_HELLO_UUID_MAX_SIZE:
        raise SessionProtocolError("DEVICE_HELLO UUID size exceeds protocol maximum.")

    if len(payload) != expected_size:
        raise SessionProtocolError("DEVICE_HELLO payload size mismatch.")

    uuid = payload[1 : 1 + uuid_size]
    require_auth = payload[1 + uuid_size] != 0

    return DeviceHelloPayload(uuid=uuid, require_auth=require_auth)
