from __future__ import annotations

import secrets
import threading
import time
from dataclasses import dataclass
from queue import Queue, Empty
from typing import Optional

from logger import Logger, LogLevel
from stream import SerialManager

from .packet import PacketType
from .packet_factory import PacketFactory
from .packet_parsers import DevHelloParser, DevAlertParser, InformationParser


@dataclass(slots=True)
class SessionInfo:
    session_id: bytes
    device_uuid: int
    require_auth: bool


class Session:
    ADV_INTERVAL_SEC = 1.0
    DEFAULT_CONNECT_TIMEOUT_SEC = 15.0
    DEFAULT_MODEL = "doorlock"

    _lock = threading.Lock()
    _serial: Optional[SerialManager] = None

    _connected: bool = False
    _info: Optional[SessionInfo] = None

    _ctrl_queue: Queue[object] = Queue()
    _data_queue: Queue[bytes] = Queue()

    _hooks_registered: bool = False
    _sid_lock = threading.Lock()

    _target_model: str = DEFAULT_MODEL
    _adv_payload_by_model: dict[str, bytes] = {
        "doorlock": b"",
        "thermostat": b"",
    }

    @classmethod
    def set_target_model(cls, model: str) -> None:
        with cls._lock:
            cls._target_model = str(model).strip().lower()

    @classmethod
    def configure_adv_payload(cls, model: str, payload: bytes) -> None:
        model_key = str(model).strip().lower()
        with cls._lock:
            cls._adv_payload_by_model[model_key] = bytes(payload)

    @classmethod
    def _current_adv_payload(cls) -> bytes:
        with cls._lock:
            model = cls._target_model
            payload = cls._adv_payload_by_model.get(model, b"")
        return payload

    @classmethod
    def bind_serial(cls, serial_manager: SerialManager) -> None:
        with cls._lock:
            cls._serial = serial_manager
            cls._hooks_registered = False
        cls._ensure_hooks()

    @classmethod
    def _get_serial(cls) -> Optional[SerialManager]:
        with cls._lock:
            return cls._serial

    @classmethod
    def is_connected(cls) -> bool:
        s = cls._get_serial()
        if s is None:
            return False
        with cls._lock:
            return cls._connected and s.is_connected()

    @classmethod
    def info(cls) -> Optional[SessionInfo]:
        with cls._lock:
            return cls._info

    @classmethod
    def connect(cls, timeout: float = DEFAULT_CONNECT_TIMEOUT_SEC) -> bool:
        if cls.is_connected():
            return True

        s = cls._get_serial()
        if s is None:
            Logger.write(LogLevel.WARNING, "Session connect failed: serial manager not bound")
            return False

        if not s.is_connected():
            Logger.write(LogLevel.WARNING, "Session connect failed: serial not connected")
            return False

        cls._ensure_hooks()
        cls._drain_queues()

        adv_payload = cls._current_adv_payload()
        if not adv_payload:
            Logger.write(LogLevel.WARNING, "Session connect failed: PC_ADV payload is empty")
            return False

        session_id = cls._alloc_session_id()

        deadline = time.monotonic() + float(timeout)
        next_adv = 0.0

        while time.monotonic() < deadline:
            now = time.monotonic()
            if now >= next_adv:
                try:
                    if not s.write_raw(adv_payload):
                        Logger.write(LogLevel.WARNING, "PC_ADV raw write failed")
                except Exception as e:
                    Logger.write(LogLevel.WARNING, f"PC_ADV raw write failed: {type(e).__name__}: {e}")
                next_adv = now + cls.ADV_INTERVAL_SEC

            ctrl = cls._ctrl_get(timeout=0.1)
            if ctrl is None:
                continue

            if isinstance(ctrl, DevHelloParser):
                device_uuid = ctrl.device_uuid
                require_auth = ctrl.require_auth

                try:
                    hello = PacketFactory.build(PacketType.PC_HELLO, session_id=session_id)
                    if not s.write(hello.build()):
                        Logger.write(LogLevel.WARNING, "Session connect failed: PC_HELLO write failed")
                        cls._set_disconnected()
                        return False
                except Exception as e:
                    Logger.write(LogLevel.WARNING, f"PC_HELLO build/write failed: {type(e).__name__}: {e}")
                    cls._set_disconnected()
                    return False

                with cls._lock:
                    cls._connected = True
                    cls._info = SessionInfo(
                        session_id=session_id,
                        device_uuid=device_uuid,
                        require_auth=require_auth,
                    )

                Logger.write(
                    LogLevel.PROGRESS,
                    f"Session connected (session_id={session_id.hex()}, uuid=0x{device_uuid:016X}, require_auth={require_auth})",
                )
                return True

            if isinstance(ctrl, DevAlertParser):
                Logger.write(LogLevel.WARNING, f"DEV_ALERT during connect: {ctrl.reason.hex()}")
                cls._set_disconnected()
                return False

        Logger.write(LogLevel.WARNING, "Session connect timeout (DEV_HELLO not received)")
        cls._set_disconnected()
        return False

    @classmethod
    def finish(cls) -> None:
        info = cls.info()
        if info is None:
            return

        s = cls._get_serial()
        if s is not None and s.is_connected():
            try:
                pkt = PacketFactory.build(PacketType.PC_BYE, session_id=info.session_id, data=b"")
                s.write(pkt.build())
            except Exception as e:
                Logger.write(LogLevel.WARNING, f"PC_BYE build/write failed: {type(e).__name__}: {e}")

        cls._set_disconnected()
        Logger.write(LogLevel.PROGRESS, f"Session finished (session_id={info.session_id.hex()})")

    @classmethod
    def alert(cls, reason: bytes = b"") -> None:
        info = cls.info()
        if info is None:
            return

        s = cls._get_serial()
        if s is not None and s.is_connected():
            try:
                pkt = PacketFactory.build(PacketType.PC_ALERT, reason=reason)
                s.write(pkt.build())
            except Exception as e:
                Logger.write(LogLevel.WARNING, f"PC_ALERT build/write failed: {type(e).__name__}: {e}")

        cls._set_disconnected()
        Logger.write(LogLevel.WARNING, f"Session alerted (session_id={info.session_id.hex()})")

    @classmethod
    def write(cls, payload: bytes) -> bool:
        info = cls.info()
        if info is None or not cls.is_connected():
            Logger.write(LogLevel.WARNING, "Session write failed: not connected")
            return False

        try:
            pkt = PacketFactory.build(PacketType.MESSAGE, session_id=info.session_id, data=payload)
            raw = pkt.build()
        except Exception as e:
            Logger.write(LogLevel.WARNING, f"Session write failed: build error: {type(e).__name__}: {e}")
            return False

        s = cls._get_serial()
        if s is None:
            Logger.write(LogLevel.WARNING, "Session write failed: serial manager not bound")
            return False

        ok = s.write(raw)
        if not ok:
            Logger.write(LogLevel.WARNING, "Session write failed: serial write failed")
        return ok

    @classmethod
    def read(cls, timeout: float | None = None) -> Optional[bytes]:
        info = cls.info()
        if info is None or not cls.is_connected():
            return None

        try:
            return cls._data_queue.get(timeout=timeout)
        except Empty:
            return None

    @classmethod
    def _ensure_hooks(cls) -> None:
        s = cls._get_serial()
        if s is None:
            return

        with cls._lock:
            if cls._hooks_registered:
                return
            cls._hooks_registered = True

        s.subscribe_event(cls._on_serial_event)

    @classmethod
    def _on_serial_event(cls, event: str) -> None:
        if event == "disconnected":
            cls._set_disconnected()

    @classmethod
    def on_serial_frame(cls, msg: bytes) -> None:
        cls._on_serial_message(msg)

    @classmethod
    def _on_serial_message(cls, msg: bytes) -> None:
        try:
            parser = PacketFactory.parse(msg)
        except Exception as e:
            Logger.write(LogLevel.WARNING, f"RX drop invalid packet ({type(e).__name__}: {e})")
            return

        if isinstance(parser, (DevHelloParser, DevAlertParser)):
            cls._ctrl_queue.put(parser)
            return

        if isinstance(parser, InformationParser):
            info = cls.info()
            if info is None:
                Logger.write(LogLevel.WARNING, "RX drop INFORMATION while disconnected")
                return

            if parser.session_id != info.session_id:
                Logger.write(
                    LogLevel.WARNING,
                    f"RX drop other-session INFORMATION (got={parser.session_id.hex()}, expected={info.session_id.hex()})",
                )
                return

            cls._data_queue.put(parser.data)
            return

        Logger.write(LogLevel.WARNING, "RX drop: unsupported parser result")

    @classmethod
    def _ctrl_get(cls, timeout: float | None) -> Optional[object]:
        try:
            return cls._ctrl_queue.get(timeout=timeout)
        except Empty:
            return None

    @classmethod
    def _drain_queues(cls) -> None:
        cls._drain_queue(cls._ctrl_queue)
        cls._drain_queue(cls._data_queue)

    @staticmethod
    def _drain_queue(q: Queue) -> None:
        try:
            while True:
                q.get_nowait()
        except Empty:
            return

    @classmethod
    def _set_disconnected(cls) -> None:
        with cls._lock:
            cls._connected = False
            cls._info = None
        cls._drain_queues()

    @classmethod
    def _alloc_session_id(cls) -> bytes:
        with cls._sid_lock:
            return secrets.token_bytes(16)