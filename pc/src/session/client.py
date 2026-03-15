from __future__ import annotations

from frame.link import FrameLink
from frame.protocol import FrameError

from .packet import SessionPacket
from .protocol import (
    PacketType,
    SessionAlertError,
    SessionClosedError,
    SessionOpenError,
    SessionProtocolError,
    SessionStateError,
    build_pc_hello_payload,
    generate_session_id,
    is_alert_packet,
    is_bye_packet,
    parse_device_hello_payload,
)


class FactorySessionClient:
    """Stateful host-side peer for the factory session protocol."""

    def __init__(self, frame_link: FrameLink) -> None:
        self._frame_link = frame_link
        self._is_opened = False
        self._session_id: bytes | None = None
        self._device_uuid: bytes | None = None
        self._require_auth = False

    @property
    def is_opened(self) -> bool:
        """Return whether the session is currently open."""
        return self._is_opened

    @property
    def session_id(self) -> bytes | None:
        """Return the current session identifier, if any."""
        return self._session_id

    @property
    def device_uuid(self) -> bytes | None:
        """Return the UUID announced by DEVICE_HELLO, if any."""
        return self._device_uuid

    @property
    def require_auth(self) -> bool:
        """Return whether the device requested authentication."""
        return self._require_auth

    def open(self) -> None:
        """
        Open the session.

        Current supported flow:
        1. wait DEVICE_HELLO
        2. generate session_id
        3. send PC_HELLO
        """
        if self._is_opened:
            return

        self._reset(keep_runtime_state=False)

        try:
            packet = self._receive_packet()
        except FrameError as exc:
            self._reset(keep_runtime_state=False)
            raise SessionOpenError("failed to receive DEVICE_HELLO.") from exc

        if is_alert_packet(packet.type):
            self._reset(keep_runtime_state=False)
            raise SessionAlertError(packet.payload)

        if packet.type != PacketType.DEVICE_HELLO:
            self._reset(keep_runtime_state=False)
            raise SessionOpenError(f"expected DEVICE_HELLO, got {packet.type.name}.")

        info = parse_device_hello_payload(packet.payload)
        self._device_uuid = info.uuid
        self._require_auth = info.require_auth

        if self._require_auth:
            self._reset(keep_runtime_state=False)
            raise SessionOpenError("authenticated session flow is not implemented yet.")

        session_id = generate_session_id()
        payload = build_pc_hello_payload(session_id)
        hello_packet = SessionPacket(
            type=PacketType.PC_HELLO,
            payload=payload,
            flag=0,
            session_id=None,
        )

        try:
            self._send_packet(hello_packet)
        except FrameError as exc:
            self._reset(keep_runtime_state=False)
            raise SessionOpenError("failed to send PC_HELLO.") from exc

        self._session_id = session_id
        self._is_opened = True

    def close(self) -> None:
        """Close the session from the PC side."""
        if not self._is_opened and self._session_id is None:
            self._reset(keep_runtime_state=False)
            return

        if self._session_id is not None:
            bye_packet = SessionPacket(
                type=PacketType.PC_BYE,
                payload=b"",
                flag=0,
                session_id=self._session_id,
            )

            try:
                self._send_packet(bye_packet)
            except FrameError:
                pass

        self._reset(keep_runtime_state=False)

    def send_message(self, payload: bytes) -> None:
        """Send one MESSAGE packet containing application payload bytes."""
        self._ensure_opened()

        packet = SessionPacket(
            type=PacketType.MESSAGE,
            payload=bytes(payload),
            flag=0,
            session_id=self._session_id,
        )

        try:
            self._send_packet(packet)
        except FrameError as exc:
            self._reset(keep_runtime_state=False)
            raise SessionProtocolError("failed to send session MESSAGE.") from exc

    def receive_message(self) -> bytes:
        """
        Receive one MESSAGE payload.

        ALERT closes the session and raises SessionAlertError.
        BYE closes the session and raises SessionClosedError.
        """
        self._ensure_opened()

        try:
            packet = self._receive_packet()
        except FrameError as exc:
            self._reset(keep_runtime_state=False)
            raise SessionProtocolError("failed to receive session packet.") from exc

        self._validate_inbound_packet(packet)

        if is_alert_packet(packet.type):
            self._reset(keep_runtime_state=False)
            raise SessionAlertError(packet.payload)

        if is_bye_packet(packet.type):
            self._reset(keep_runtime_state=False)
            raise SessionClosedError("peer closed the session.")

        if packet.type != PacketType.MESSAGE:
            raise SessionProtocolError(f"expected MESSAGE packet, got {packet.type.name}.")

        return packet.payload

    def _send_packet(self, packet: SessionPacket) -> None:
        """Encode and send one session packet."""
        self._frame_link.send_packet(packet.encode())

    def _receive_packet(self) -> SessionPacket:
        """Receive and decode one session packet."""
        raw = self._frame_link.receive_packet()
        return SessionPacket.decode(raw)

    def _validate_inbound_packet(self, packet: SessionPacket) -> None:
        """Validate session-id consistency for inbound session packets."""
        if packet.type == PacketType.DEVICE_HELLO:
            return

        if packet.is_sessionless:
            return

        if self._session_id is None:
            raise SessionProtocolError("received session packet before local session_id was established.")

        if packet.session_id != self._session_id:
            raise SessionProtocolError("received packet with mismatched session_id.")

    def _ensure_opened(self) -> None:
        """Ensure that the session is open."""
        if not self._is_opened or self._session_id is None:
            raise SessionStateError("session is not opened.")

    def _reset(self, *, keep_runtime_state: bool) -> None:
        """Reset local session state."""
        _ = keep_runtime_state
        self._is_opened = False
        self._session_id = None
        self._device_uuid = None
        self._require_auth = False
