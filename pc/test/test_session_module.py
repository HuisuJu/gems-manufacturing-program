import threading
import time

from session.session import Session, SessionInfo
from session.packet import PacketBuilder, PacketType


class _FakeSerialManager:
    def __init__(self):
        self._connected = True
        self.raw_writes = []
        self.packet_writes = []
        self.listeners = []

    def subscribe_event(self, cb):
        self.listeners.append(cb)

    def is_connected(self):
        return self._connected

    def write_raw(self, data: bytes):
        self.raw_writes.append(bytes(data))
        return True

    def write(self, data: bytes):
        self.packet_writes.append(bytes(data))
        return True


def _build_dev_hello_packet(device_uuid: int, require_auth: bool) -> bytes:
    payload = bytes([0x01, 11]) + device_uuid.to_bytes(8, "big") + bytes([1 if require_auth else 0])
    return PacketBuilder(type=PacketType.DEV_HELLO, payload=payload).build()


def _reset_session_state():
    Session._set_disconnected()
    with Session._lock:
        Session._serial = None
        Session._hooks_registered = False
        Session._target_model = Session.DEFAULT_MODEL
        Session._adv_payload_by_model = {"doorlock": b"", "thermostat": b""}


def test_connect_sends_raw_adv_then_pc_hello_and_sets_session_info():
    _reset_session_state()
    sm = _FakeSerialManager()
    Session.bind_serial(sm)

    Session.set_target_model("doorlock")
    Session.configure_adv_payload("doorlock", b"\xDE\xAD\xBE\xEF")

    def _push_dev_hello():
        time.sleep(0.05)
        Session.on_serial_frame(_build_dev_hello_packet(0x1122334455667788, True))

    th = threading.Thread(target=_push_dev_hello, daemon=True)
    th.start()

    ok = Session.connect(timeout=1.0)
    assert ok is True

    info = Session.info()
    assert info is not None
    assert isinstance(info.session_id, bytes)
    assert len(info.session_id) == 16
    assert info.device_uuid == 0x1122334455667788
    assert info.require_auth is True

    assert sm.raw_writes, "PC_ADV raw writes should exist"
    assert sm.raw_writes[0] == b"\xDE\xAD\xBE\xEF"
    assert sm.packet_writes, "PC_HELLO packet write should exist"


def test_connect_fails_when_adv_payload_not_configured():
    _reset_session_state()
    sm = _FakeSerialManager()
    Session.bind_serial(sm)

    Session.set_target_model("doorlock")
    ok = Session.connect(timeout=0.2)

    assert ok is False
    assert sm.raw_writes == []


def test_on_serial_message_information_goes_to_read_queue_for_matching_session():
    _reset_session_state()
    sm = _FakeSerialManager()
    Session.bind_serial(sm)

    session_id = b"\x01" * 16
    with Session._lock:
        Session._connected = True
        Session._info = SessionInfo(
            session_id=session_id,
            device_uuid=1,
            require_auth=False,
        )

    payload = b"protobuf-encoded-data"
    packet = PacketBuilder(type=PacketType.MESSAGE, session_id=session_id, payload=payload).build()
    Session.on_serial_frame(packet)

    got = Session.read(timeout=0.1)
    assert got == payload
