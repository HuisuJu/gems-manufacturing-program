import threading
from typing import Callable, Optional

import serial
import serial.tools.list_ports
import serial.threaded
from cobs import cobs

from logger.logger import Logger, LogLevel


class _SerialConnection(serial.threaded.Packetizer):
    TERMINATOR = b"\x00"

    def __init__(self, manager: "SerialManager"):
        super().__init__()
        self._manager = manager

    def connection_made(self, transport):
        super().connection_made(transport)
        self._manager._on_connected()

    def connection_lost(self, exc):
        self._manager._on_disconnected()
        super().connection_lost(exc)

    def handle_packet(self, packet: bytes):
        if not packet:
            return

        try:
            msg = cobs.decode(packet)
        except Exception as e:
            Logger.write(
                LogLevel.ERROR,
                f"COBS decode failed ({type(e).__name__}: {e}), raw={packet.hex()}",
            )
            return

        self._manager._on_frame_received(msg)


class SerialManager:
    CONNECT_TIMEOUT = 3.0

    def __init__(self, packet_handler: Callable[[bytes], None]):
        self._packet_handler = packet_handler

        self._lock = threading.Lock()
        self._serial: Optional[serial.Serial] = None
        self._thread: Optional[serial.threaded.ReaderThread] = None
        self._protocol = None

        self._ready = threading.Event()
        self._connected_flag = False

        self._event_listeners: list[Callable[[str], None]] = []

    @staticmethod
    def list_ports() -> list[str]:
        ports = serial.tools.list_ports.comports()
        return [p.device for p in ports]

    def subscribe_event(self, listener: Callable[[str], None]) -> None:
        with self._lock:
            if listener not in self._event_listeners:
                self._event_listeners.append(listener)

    def unsubscribe_event(self, listener: Callable[[str], None]) -> None:
        with self._lock:
            if listener in self._event_listeners:
                self._event_listeners.remove(listener)

    def is_connected(self) -> bool:
        with self._lock:
            s = self._serial
            t = self._thread
            ok = self._connected_flag
        return s is not None and s.is_open and t is not None and ok

    def open(self, port: str, baudrate: int = 115200) -> bool:
        self.close()

        with self._lock:
            self._ready.clear()
            self._connected_flag = False
            self._protocol = None

        try:
            s = serial.Serial(port, baudrate, timeout=0.2)
            t = serial.threaded.ReaderThread(s, lambda: _SerialConnection(self))

            with self._lock:
                self._serial = s
                self._thread = t

            t.start()

            try:
                _transport, protocol = t.connect()
            except Exception as e:
                Logger.write(
                    LogLevel.WARNING,
                    f"ReaderThread connect failed ({port}, {baudrate}): {type(e).__name__}: {e}",
                )
                self.close()
                return False

            with self._lock:
                self._protocol = protocol

            if not self._ready.wait(timeout=self.CONNECT_TIMEOUT):
                Logger.write(LogLevel.WARNING, f"Serial connect timeout ({port}, {baudrate})")
                self.close()
                return False

            return True

        except Exception as e:
            Logger.write(
                LogLevel.WARNING,
                f"Failed to open serial port ({port}, {baudrate}): {type(e).__name__}: {e}",
            )
            self.close()
            return False

    def close(self) -> None:
        with self._lock:
            t = self._thread
            s = self._serial

            self._thread = None
            self._serial = None
            self._protocol = None
            self._ready.clear()
            self._connected_flag = False

        if t:
            try:
                try:
                    t.close()
                except Exception:
                    t.stop()
            except Exception as e:
                Logger.write(LogLevel.WARNING, f"ReaderThread stop/close failed: {type(e).__name__}: {e}")

        if s and s.is_open:
            try:
                s.close()
            except Exception as e:
                Logger.write(LogLevel.WARNING, f"Serial close failed: {type(e).__name__}: {e}")

    def write(self, buf: bytes) -> bool:
        with self._lock:
            t = self._thread
            s = self._serial
            ok = self._connected_flag

        if not (t and s and s.is_open and ok):
            Logger.write(LogLevel.WARNING, "Serial write failed: not connected")
            return False

        try:
            t.write(cobs.encode(buf) + b"\x00")
            return True
        except Exception as e:
            Logger.write(LogLevel.WARNING, f"Serial write failed: {type(e).__name__}: {e}")
            return False

    def publish(self, name: str) -> None:
        with self._lock:
            listeners = list(self._event_listeners)

        for cb in listeners:
            try:
                cb(name)
            except Exception as e:
                Logger.write(LogLevel.WARNING, f"Event listener error: {type(e).__name__}: {e}")

    def _on_connected(self) -> None:
        with self._lock:
            already = self._connected_flag
            self._connected_flag = True
            self._ready.set()

        if not already:
            self.publish("connected")
            Logger.write(LogLevel.PROGRESS, "Serial port is connected!!")

    def _on_disconnected(self) -> None:
        with self._lock:
            already = self._connected_flag
            self._connected_flag = False
            self._ready.clear()

        if already:
            self.publish("disconnected")
            Logger.write(LogLevel.PROGRESS, "Serial port is disconnected!!")

    def _on_frame_received(self, msg: bytes) -> None:
        try:
            self._packet_handler(msg)
        except Exception as e:
            Logger.write(LogLevel.WARNING, f"Packet handler error: {type(e).__name__}: {e}")
