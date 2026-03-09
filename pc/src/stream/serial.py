"""Serial transport manager with factory frame transport.

This module provides :class:`SerialManager` for packet-based serial I/O over
factory frame protocol (magic ``0xFAC0`` + header + payload + CRC).
Incoming data is parsed/reassembled and forwarded as one logical packet.
Outgoing packets are fragmented and sent with ACK/NACK flow control.
"""

import threading
import time
from queue import Empty, Queue
from typing import Callable, Optional

import serial
import serial.tools.list_ports

from logger.manager import Logger, LogLevel
from .frame_parser import (
    FLOW_CONTROL_TIMEOUT_SEC,
    MAX_RETRY_COUNT,
    FRAME_TYPE_ACK,
    PacketAssembler,
    PacketFragmenter,
    StreamFrameParser,
    build_control_frame,
    control_sequence_from_frame,
)


class SerialManager:
    """Thread-safe serial connection manager.

    :param packet_handler: Callback invoked with decoded payload bytes.
    :type packet_handler: Callable[[bytes], None]
    """

    def __init__(self, packet_handler: Callable[[bytes], None]):
        """Create a new serial manager.

        :param packet_handler: Packet callback for decoded frames.
        :type packet_handler: Callable[[bytes], None]
        """
        self._packet_handler = packet_handler

        self._lock = threading.Lock()
        self._serial: Optional[serial.Serial] = None
        self._rx_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

        self._connected_flag = False

        self._ack_queue: Queue[tuple[bool, int]] = Queue()
        self._packet_queue: Queue[bytes] = Queue()

        self._event_listeners: list[Callable[[str], None]] = []

    @staticmethod
    def list_ports() -> list[str]:
        """Return currently available serial device names.

        :return: Device path list (e.g. ``/dev/tty.usbserial-xxxx``).
        :rtype: list[str]
        """
        ports = serial.tools.list_ports.comports()
        return [p.device for p in ports]

    def subscribe_event(self, listener: Callable[[str], None]) -> None:
        """Register connection state listener.

        Listener receives ``"connected"`` or ``"disconnected"``.

        :param listener: Event callback.
        :type listener: Callable[[str], None]
        """
        with self._lock:
            if listener not in self._event_listeners:
                self._event_listeners.append(listener)

    def unsubscribe_event(self, listener: Callable[[str], None]) -> None:
        """Unregister connection state listener.

        :param listener: Previously registered callback.
        :type listener: Callable[[str], None]
        """
        with self._lock:
            if listener in self._event_listeners:
                self._event_listeners.remove(listener)

    def is_connected(self) -> bool:
        """Return current connection status.

        :return: ``True`` if serial is open and protocol is connected.
        :rtype: bool
        """
        with self._lock:
            s = self._serial
            t = self._rx_thread
            ok = self._connected_flag
        return s is not None and s.is_open and t is not None and t.is_alive() and ok

    def open(self, port: str, baudrate: int = 115200) -> bool:
        """Open serial port and start reader thread.

        :param port: Serial device name.
        :type port: str
        :param baudrate: UART baudrate.
        :type baudrate: int
        :return: ``True`` on success, otherwise ``False``.
        :rtype: bool
        """
        self.close()

        try:
            s = serial.Serial(port, baudrate, timeout=0.05)
            t = threading.Thread(target=self._rx_loop, name="SerialRx", daemon=True)

            with self._lock:
                self._serial = s
                self._rx_thread = t
                self._connected_flag = True
                self._stop_event.clear()

            t.start()
            self._on_connected()
            return True

        except Exception as e:
            Logger.write(
                LogLevel.WARNING,
                f"Failed to open serial port ({port}, {baudrate}): {type(e).__name__}: {e}",
            )
            self.close()
            return False

    def close(self) -> None:
        """Close current serial connection and stop reader thread."""
        with self._lock:
            t = self._rx_thread
            s = self._serial

            self._rx_thread = None
            self._serial = None
            self._connected_flag = False
            self._stop_event.set()

        if s and s.is_open:
            try:
                s.close()
            except Exception as e:
                Logger.write(LogLevel.WARNING, f"Serial close failed: {type(e).__name__}: {e}")

        if t and t.is_alive():
            t.join(timeout=0.5)

        self._on_disconnected()

    def write(self, buf: bytes) -> bool:
        """Send one payload frame.

        Packet is fragmented into factory frames and each frame waits for
        ACK/NACK flow control.

        :param buf: Raw payload bytes.
        :type buf: bytes
        :return: ``True`` on success, otherwise ``False``.
        :rtype: bool
        """
        with self._lock:
            s = self._serial
            ok = self._connected_flag

        if not buf:
            Logger.write(LogLevel.WARNING, "Serial write failed: empty payload")
            return False

        if not (s and s.is_open and ok):
            Logger.write(LogLevel.WARNING, "Serial write failed: not connected")
            return False

        try:
            fragmenter = PacketFragmenter(buf)

            while not fragmenter.done():
                frame_raw, sequence = fragmenter.next_frame()
                acknowledged = False

                for _ in range(MAX_RETRY_COUNT):
                    if not self._write_serial_bytes(frame_raw):
                        continue

                    ack = self._wait_ack(sequence, FLOW_CONTROL_TIMEOUT_SEC)
                    if ack is True:
                        acknowledged = True
                        break

                if not acknowledged:
                    Logger.write(LogLevel.WARNING, f"Serial write failed: frame seq={sequence} ack timeout/retry exhausted")
                    return False

            return True
        except Exception as e:
            Logger.write(LogLevel.WARNING, f"Serial write failed: {type(e).__name__}: {e}")
            return False

    def write_raw(self, data: bytes) -> bool:
        """Write raw bytes directly to UART (no framing).

        Used for pre-session discovery/advertisement payloads.
        """
        if not isinstance(data, (bytes, bytearray, memoryview)):
            Logger.write(LogLevel.WARNING, "Serial raw write failed: data must be bytes-like")
            return False
        payload = bytes(data)
        if not payload:
            return False
        return self._write_serial_bytes(payload)

    def read(self, timeout: Optional[float] = None) -> Optional[bytes]:
        """Read one reassembled packet.

        :param timeout: Optional timeout seconds.
        :type timeout: float | None
        :return: One packet bytes if available, otherwise ``None``.
        :rtype: bytes | None
        """
        try:
            return self._packet_queue.get(timeout=timeout)
        except Empty:
            return None

    def publish(self, name: str) -> None:
        """Notify subscribed listeners.

        :param name: Event name.
        :type name: str
        """
        with self._lock:
            listeners = list(self._event_listeners)

        for cb in listeners:
            try:
                cb(name)
            except Exception as e:
                Logger.write(LogLevel.WARNING, f"Event listener error: {type(e).__name__}: {e}")

    def _on_connected(self) -> None:
        """Internal hook called when transport is connected."""
        with self._lock:
            already = self._connected_flag
            self._connected_flag = True

        if not already:
            self.publish("connected")
            Logger.write(LogLevel.PROGRESS, "Serial port is connected!!")

    def _on_disconnected(self) -> None:
        """Internal hook called when transport is disconnected."""
        with self._lock:
            already = self._connected_flag
            self._connected_flag = False

        if already:
            self.publish("disconnected")
            Logger.write(LogLevel.PROGRESS, "Serial port is disconnected!!")

    def _write_serial_bytes(self, data: bytes) -> bool:
        with self._lock:
            s = self._serial
            ok = self._connected_flag

        if not (s and s.is_open and ok):
            return False

        try:
            s.write(data)
            return True
        except Exception as e:
            Logger.write(LogLevel.WARNING, f"Serial write bytes failed: {type(e).__name__}: {e}")
            return False

    def _wait_ack(self, sequence: int, timeout_sec: float) -> Optional[bool]:
        deadline = time.monotonic() + timeout_sec
        stash: list[tuple[bool, int]] = []

        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break

            try:
                is_ack, seq = self._ack_queue.get(timeout=remaining)
            except Empty:
                break

            if seq == sequence:
                for item in stash:
                    self._ack_queue.put(item)
                return is_ack

            stash.append((is_ack, seq))

        for item in stash:
            self._ack_queue.put(item)
        return None

    def _rx_loop(self) -> None:
        parser = StreamFrameParser()
        assembler = PacketAssembler()

        while not self._stop_event.is_set():
            with self._lock:
                s = self._serial

            if s is None or not s.is_open:
                break

            try:
                raw = s.read(256)
            except Exception as e:
                Logger.write(LogLevel.WARNING, f"Serial read failed: {type(e).__name__}: {e}")
                break

            if not raw:
                continue

            for frame in parser.feed(raw):
                try:
                    if frame.frame_type in (FRAME_TYPE_ACK, FRAME_TYPE_NACK):
                        seq = control_sequence_from_frame(frame)
                        self._ack_queue.put((frame.frame_type == FRAME_TYPE_ACK, seq))
                        continue

                    status, packet, seq = assembler.process(frame)
                    if status == "duplicate" and seq is not None:
                        self._write_serial_bytes(build_control_frame(True, seq))
                        continue
                    if status == "error" and seq is not None:
                        self._write_serial_bytes(build_control_frame(False, seq))
                        continue
                    if status in ("ok", "done") and seq is not None:
                        self._write_serial_bytes(build_control_frame(True, seq))

                    if status == "done" and packet is not None:
                        self._packet_queue.put(packet)
                        try:
                            self._packet_handler(packet)
                        except Exception as e:
                            Logger.write(LogLevel.WARNING, f"Packet handler error: {type(e).__name__}: {e}")
                except Exception as e:
                    Logger.write(LogLevel.WARNING, f"Frame process failed: {type(e).__name__}: {e}")

        self._on_disconnected()
