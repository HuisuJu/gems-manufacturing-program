from stream.serial import SerialManager


class _FakeSerial:
    def __init__(self):
        self.is_open = True
        self.writes = []

    def write(self, data: bytes):
        self.writes.append(bytes(data))
        return len(data)


def test_write_raw_writes_bytes_when_connected():
    sm = SerialManager(lambda _msg: None)
    fake = _FakeSerial()

    sm._serial = fake
    sm._connected_flag = True

    assert sm.write_raw(b"\xAA\xBB\xCC") is True
    assert fake.writes[-1] == b"\xAA\xBB\xCC"


def test_write_returns_false_if_ack_not_received(monkeypatch):
    sm = SerialManager(lambda _msg: None)
    fake = _FakeSerial()

    sm._serial = fake
    sm._connected_flag = True

    monkeypatch.setattr(sm, "_wait_ack", lambda sequence, timeout_sec: None)

    assert sm.write(b"hello") is False


def test_write_returns_true_when_ack_received(monkeypatch):
    sm = SerialManager(lambda _msg: None)
    fake = _FakeSerial()

    sm._serial = fake
    sm._connected_flag = True

    monkeypatch.setattr(sm, "_wait_ack", lambda sequence, timeout_sec: True)

    assert sm.write(b"hello") is True
    assert len(fake.writes) >= 1
