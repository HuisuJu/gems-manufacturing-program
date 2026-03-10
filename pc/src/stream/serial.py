"""Serial raw byte stream implementation.

This module provides :class:`SerialStream`, a thread-safe serial stream
implementation that reads and writes raw bytes only.

No framing, packet parsing, encoding, retransmission, or protocol-specific
flow control is handled here. Those responsibilities belong to upper layers.
"""

from __future__ import annotations

import threading
from queue import Empty, Queue
from typing import Optional

import serial
import serial.tools.list_ports

from logger.manager import Logger, LogLevel
from .base import Stream, StreamEventListener


class SerialStream(Stream):
    """Thread-safe raw serial stream manager.

    Incoming UART data is collected as raw byte chunks and made available
    through :meth:`read`. Outgoing data is written as-is through :meth:`write`.
    """

    def __init__(self) -> None:
        """Initialize the serial stream manager."""
        self._lock = threading.Lock()
        self._serial: Optional[serial.Serial] = None
        self._rx_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

        self._connected_flag = False
        self._read_queue: Queue[bytes] = Queue()
        self._event_listeners: list[StreamEventListener] = []

    @staticmethod
    def list_ports() -> list[str]:
        """Return currently available serial device names.

        Returns:
            Device path list.
        """
        ports = serial.tools.list_ports.comports()
        return [p.device for p in ports]

    def subscribe_event(self, listener: StreamEventListener) -> None:
        """Register a stream state listener.

        Args:
            listener:
                Event callback.
        """
        with self._lock:
            if listener not in self._event_listeners:
                self._event_listeners.append(listener)

    def unsubscribe_event(self, listener: StreamEventListener) -> None:
        """Unregister a stream state listener.

        Args:
            listener:
                Previously registered callback.
        """
        with self._lock:
            if listener in self._event_listeners:
                self._event_listeners.remove(listener)

    def is_connected(self) -> bool:
        """Return current connection status.

        Returns:
            True if the serial port is open and the reader thread is alive.
        """
        with self._lock:
            s = self._serial
            t = self._rx_thread
            ok = self._connected_flag

        return s is not None and s.is_open and t is not None and t.is_alive() and ok

    def open(self, port: str, baudrate: int = 115200) -> bool:
        """Open the serial port and start the reader thread.

        Args:
            port:
                Serial device name.
            baudrate:
                UART baudrate.

        Returns:
            True on success, otherwise False.
        """
        self.close()

        try:
            s = serial.Serial(port, baudrate, timeout=0.05)
            t = threading.Thread(target=self._rx_loop, name="SerialRx", daemon=True)

            with self._lock:
                self._serial = s
                self._rx_thread = t
                self._stop_event.clear()
                self._connected_flag = True

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
        """Close the serial port and stop the reader thread."""
        with self._lock:
            t = self._rx_thread
            s = self._serial
            was_connected = self._connected_flag

            self._rx_thread = None
            self._serial = None
            self._connected_flag = False
            self._stop_event.set()

        if s and s.is_open:
            try:
                s.close()
            except Exception as e:
                Logger.write(
                    LogLevel.WARNING,
                    f"Serial close failed: {type(e).__name__}: {e}",
                )

        if t and t.is_alive():
            t.join(timeout=0.5)

        if was_connected:
            self._on_disconnected()

    def write(self, data: bytes) -> bool:
        """Write raw bytes directly to the serial port.

        Args:
            data:
                Raw bytes to transmit.

        Returns:
            True on success, otherwise False.
        """
        if not isinstance(data, (bytes, bytearray, memoryview)):
            Logger.write(
                LogLevel.WARNING,
                "Serial write failed: data must be bytes-like",
            )
            return False

        payload = bytes(data)
        if not payload:
            Logger.write(LogLevel.WARNING, "Serial write failed: empty payload")
            return False

        with self._lock:
            s = self._serial
            ok = self._connected_flag

        if not (s and s.is_open and ok):
            Logger.write(LogLevel.WARNING, "Serial write failed: not connected")
            return False

        try:
            s.write(payload)
            return True
        except Exception as e:
            Logger.write(
                LogLevel.WARNING,
                f"Serial write failed: {type(e).__name__}: {e}",
            )
            return False

    def read(self, timeout: Optional[float] = None) -> Optional[bytes]:
        """Read one raw byte chunk from the receive queue.

        Args:
            timeout:
                Optional timeout in seconds.

        Returns:
            Raw received bytes, or None if no data is available.
        """
        try:
            return self._read_queue.get(timeout=timeout)
        except Empty:
            return None

    def publish(self, name: str) -> None:
        """Notify subscribed listeners.

        Args:
            name:
                Event name.
        """
        with self._lock:
            listeners = list(self._event_listeners)

        for listener in listeners:
            try:
                listener(name)
            except Exception as e:
                Logger.write(
                    LogLevel.WARNING,
                    f"Event listener error: {type(e).__name__}: {e}",
                )

    def _on_connected(self) -> None:
        """Handle the connected transition."""
        self.publish("connected")
        Logger.write(LogLevel.PROGRESS, "Serial port is connected.")

    def _on_disconnected(self) -> None:
        """Handle the disconnected transition."""
        self.publish("disconnected")
        Logger.write(LogLevel.PROGRESS, "Serial port is disconnected.")

    def _rx_loop(self) -> None:
        """Continuously read raw bytes from the serial port."""
        while not self._stop_event.is_set():
            with self._lock:
                s = self._serial

            if s is None or not s.is_open:
                break

            try:
                raw = s.read(256)
            except Exception as e:
                Logger.write(
                    LogLevel.WARNING,
                    f"Serial read failed: {type(e).__name__}: {e}",
                )
                break

            if raw:
                self._read_queue.put(raw)

        with self._lock:
            was_connected = self._connected_flag
            self._connected_flag = False

        if was_connected:
            self._on_disconnected()