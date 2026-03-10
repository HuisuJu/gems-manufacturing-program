"""In-memory emulator stream implementation.

This module provides :class:`EmulatorStream`, a Stream-compatible
transport used to emulate a device connection without physical hardware.

The emulator stream carries raw bytes only. It can be used by the PC-side
application exactly like a real serial stream, while test or emulator logic
can inject incoming bytes and observe outgoing bytes in memory.
"""

from __future__ import annotations

import threading
from queue import Empty, Queue
from typing import Callable, Optional

from logger.manager import Logger, LogLevel
from stream import Stream, StreamEventListener


EmulatorWriteHandler = Callable[[bytes], None]


class EmulatorStream(Stream):
    """Thread-safe in-memory stream transport for device emulation.

    This class behaves like a connected byte stream from the PC application's
    point of view, but it does not use a physical serial port. Instead,
    emulator logic may inject received bytes directly through :meth:`inject_rx`
    and observe outgoing bytes through :meth:`set_write_handler` or
    :meth:`read_tx`.
    """

    _default_ports: list[str] = ["device_emulator"]

    @staticmethod
    def list_ports() -> list[str]:
        """Return available virtual emulator endpoints.

        Returns:
            A list of virtual endpoint names.
        """
        return list(EmulatorStream._default_ports)

    @classmethod
    def set_ports(cls, ports: list[str]) -> None:
        """Replace the global emulator endpoint list.

        Empty or blank entries are ignored.

        Args:
            ports:
                New virtual endpoint names.
        """
        normalized = [str(port).strip() for port in ports if str(port).strip()]
        cls._default_ports = normalized or ["device_emulator"]

    @classmethod
    def add_port(cls, port: str) -> None:
        """Add one virtual emulator endpoint.

        Duplicate entries are ignored.

        Args:
            port:
                Virtual endpoint name.
        """
        normalized = str(port).strip()
        if not normalized:
            return

        if normalized not in cls._default_ports:
            cls._default_ports.append(normalized)

    @classmethod
    def remove_port(cls, port: str) -> None:
        """Remove one virtual emulator endpoint.

        Args:
            port:
                Virtual endpoint name to remove.
        """
        normalized = str(port).strip()
        if not normalized:
            return

        if normalized in cls._default_ports:
            cls._default_ports.remove(normalized)

        if not cls._default_ports:
            cls._default_ports = ["device_emulator"]

    def __init__(self) -> None:
        """Initialize the emulator stream manager."""
        self._lock = threading.Lock()

        self._connected_flag = False
        self._opened_port: Optional[str] = None

        self._rx_queue: Queue[bytes] = Queue()
        self._tx_queue: Queue[bytes] = Queue()
        self._event_listeners: list[StreamEventListener] = []

        self._write_handler: Optional[EmulatorWriteHandler] = None

    def subscribe_event(self, listener: StreamEventListener) -> None:
        """Register a stream state listener.

        Args:
            listener:
                Callback invoked for stream events.
        """
        with self._lock:
            if listener not in self._event_listeners:
                self._event_listeners.append(listener)

    def unsubscribe_event(self, listener: StreamEventListener) -> None:
        """Unregister a previously registered stream state listener.

        Args:
            listener:
                Callback to remove.
        """
        with self._lock:
            if listener in self._event_listeners:
                self._event_listeners.remove(listener)

    def is_connected(self) -> bool:
        """Return the current connection status.

        Returns:
            True if the emulator stream is connected.
        """
        with self._lock:
            return self._connected_flag

    def open(self, port: str, baudrate: int = 115200) -> bool:
        """Open a virtual emulator endpoint.

        The baudrate argument is accepted for interface compatibility and is
        ignored by this in-memory implementation.

        Args:
            port:
                Virtual endpoint name.
            baudrate:
                Unused compatibility parameter.

        Returns:
            True on success, otherwise False.
        """
        del baudrate

        normalized = str(port).strip()
        if not normalized:
            Logger.write(LogLevel.WARNING, "Emulator open failed: empty port name.")
            return False

        if normalized not in self.list_ports():
            Logger.write(
                LogLevel.WARNING,
                f"Emulator open failed: unknown port '{normalized}'.",
            )
            return False

        self.close()

        with self._lock:
            self._connected_flag = True
            self._opened_port = normalized

        self._on_connected()
        return True

    def close(self) -> None:
        """Close the current virtual emulator endpoint."""
        with self._lock:
            was_connected = self._connected_flag
            self._connected_flag = False
            self._opened_port = None

        if was_connected:
            self._on_disconnected()

    def write(self, data: bytes) -> bool:
        """Write raw bytes to the emulator stream.

        The written bytes are stored in the TX queue so emulator-side logic can
        inspect them. If a write handler is registered, it is invoked
        synchronously with the written payload.

        Args:
            data:
                Raw byte sequence from the PC-side application.

        Returns:
            True on success, otherwise False.
        """
        if not isinstance(data, (bytes, bytearray, memoryview)):
            Logger.write(
                LogLevel.WARNING,
                "Emulator write failed: data must be bytes-like.",
            )
            return False

        payload = bytes(data)
        if not payload:
            Logger.write(LogLevel.WARNING, "Emulator write failed: empty payload.")
            return False

        with self._lock:
            connected = self._connected_flag
            handler = self._write_handler

        if not connected:
            Logger.write(LogLevel.WARNING, "Emulator write failed: not connected.")
            return False

        self._tx_queue.put(payload)

        if handler is not None:
            try:
                handler(payload)
            except Exception as e:
                Logger.write(
                    LogLevel.WARNING,
                    f"Emulator write handler failed: {type(e).__name__}: {e}",
                )
                return False

        return True

    def read(self, timeout: Optional[float] = None) -> Optional[bytes]:
        """Read one raw byte chunk from the RX queue.

        Args:
            timeout:
                Optional timeout in seconds.

        Returns:
            One raw byte chunk if available, otherwise None.
        """
        try:
            return self._rx_queue.get(timeout=timeout)
        except Empty:
            return None

    def publish(self, name: str) -> None:
        """Publish one stream event to subscribed listeners.

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
                    f"Emulator event listener error: {type(e).__name__}: {e}",
                )

    def set_write_handler(self, handler: Optional[EmulatorWriteHandler]) -> None:
        """Register or clear the emulator-side write handler.

        The handler is invoked whenever the PC-side code writes bytes to this
        stream.

        Args:
            handler:
                Callback receiving one written payload, or None to clear it.
        """
        with self._lock:
            self._write_handler = handler

    def inject_rx(self, data: bytes) -> bool:
        """Inject incoming bytes toward the PC-side application.

        This simulates bytes produced by the emulated device.

        Args:
            data:
                Raw byte sequence to push into the RX queue.

        Returns:
            True on success, otherwise False.
        """
        if not isinstance(data, (bytes, bytearray, memoryview)):
            Logger.write(
                LogLevel.WARNING,
                "Emulator RX injection failed: data must be bytes-like.",
            )
            return False

        payload = bytes(data)
        if not payload:
            return False

        with self._lock:
            connected = self._connected_flag

        if not connected:
            Logger.write(
                LogLevel.WARNING,
                "Emulator RX injection failed: not connected.",
            )
            return False

        self._rx_queue.put(payload)
        return True

    def read_tx(self, timeout: Optional[float] = None) -> Optional[bytes]:
        """Read one payload written by the PC-side application.

        This allows emulator-side logic to consume outgoing bytes without using
        a write handler.

        Args:
            timeout:
                Optional timeout in seconds.

        Returns:
            One TX payload if available, otherwise None.
        """
        try:
            return self._tx_queue.get(timeout=timeout)
        except Empty:
            return None

    def clear_queues(self) -> None:
        """Discard all pending RX and TX payloads."""
        self._drain_queue(self._rx_queue)
        self._drain_queue(self._tx_queue)

    def get_opened_port(self) -> Optional[str]:
        """Return the currently opened virtual endpoint name.

        Returns:
            The current port name, or None if disconnected.
        """
        with self._lock:
            return self._opened_port

    def _on_connected(self) -> None:
        """Handle the connected transition."""
        self.publish("connected")
        Logger.write(LogLevel.PROGRESS, "Emulator stream is connected.")

    def _on_disconnected(self) -> None:
        """Handle the disconnected transition."""
        self.publish("disconnected")
        Logger.write(LogLevel.PROGRESS, "Emulator stream is disconnected.")

    @staticmethod
    def _drain_queue(queue: Queue[bytes]) -> None:
        """Remove all items from one queue.

        Args:
            queue:
                Target queue to drain.
        """
        while True:
            try:
                queue.get_nowait()
            except Empty:
                break