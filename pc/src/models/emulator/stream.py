"""In-memory emulator stream implementation."""

from __future__ import annotations

from queue import Empty, Queue
from typing import Callable, Optional

from stream.base import Stream, StreamEvent, StreamIOError


EmulatorWriteHandler = Callable[[bytes], None]


class EmulatorStream(Stream):
    """Lightweight virtual stream implementation."""

    _PORTS = ["virtual-port-1", "virtual-port-2"]

    @staticmethod
    def list_ports() -> list[str]:
        """Return available virtual endpoint names."""
        return list(EmulatorStream._PORTS)

    def __init__(self) -> None:
        """Initialize stream state."""
        super().__init__()
        self._connected_flag = False
        self._opened_port: Optional[str] = None
        self._rx_queue: Queue[bytes] = Queue()
        self._rx_buffer = bytearray()
        self._tx_queue: Queue[bytes] = Queue()
        self._write_handler: Optional[EmulatorWriteHandler] = None

    def is_connected(self) -> bool:
        """Return whether the stream is connected."""
        return self._connected_flag

    def open(self, port: str, baudrate: int = 115200) -> bool:
        """Open a virtual endpoint."""
        del baudrate

        normalized = str(port).strip()
        if not normalized:
            raise StreamIOError("Emulator port name must not be empty.")

        if normalized not in self.list_ports():
            raise StreamIOError(f"Unknown emulator port '{normalized}'.")

        self.close()
        self._connected_flag = True
        self._opened_port = normalized

        self._on_connected()
        return True

    def close(self) -> None:
        """Close the stream."""
        was_connected = self._connected_flag
        self._connected_flag = False
        self._opened_port = None

        if was_connected:
            self._on_disconnected()

    def write(self, data: bytes) -> bool:
        """Write bytes to the stream."""
        if not isinstance(data, (bytes, bytearray, memoryview)):
            raise StreamIOError("Write payload must be bytes-like.")

        payload = bytes(data)
        if not payload:
            raise StreamIOError("Write payload must not be empty.")

        if not self._connected_flag:
            raise StreamIOError("Cannot write while stream is disconnected.")

        self._tx_queue.put(payload)

        if self._write_handler is not None:
            try:
                self._write_handler(payload)
            except Exception as exc:
                raise StreamIOError("Emulator write handler failed.") from exc

        return True

    def read(self, size: int, timeout: Optional[float] = None) -> Optional[bytes]:
        """Read up to size bytes from the RX queue."""
        if size <= 0:
            return None

        result = bytearray()

        buffered_size = min(size, len(self._rx_buffer))
        result.extend(self._rx_buffer[:buffered_size])
        del self._rx_buffer[:buffered_size]

        if len(result) >= size:
            return bytes(result)

        try:
            chunk = self._rx_queue.get(timeout=timeout)
            remain_size = size - len(result)
            result.extend(chunk[:remain_size])

            if len(chunk) > remain_size:
                self._rx_buffer.extend(chunk[remain_size:])

            return bytes(result) if result else None
        except Empty:
            return bytes(result) if result else None
        except Exception as exc:
            raise StreamIOError("Failed to read from emulator RX queue.") from exc

    def set_write_handler(self, handler: Optional[EmulatorWriteHandler]) -> None:
        """Set or clear write handler."""
        self._write_handler = handler

    def inject_rx(self, data: bytes) -> bool:
        """Inject device bytes into RX queue."""
        if not isinstance(data, (bytes, bytearray, memoryview)):
            raise StreamIOError("RX payload must be bytes-like.")

        payload = bytes(data)
        if not payload:
            raise StreamIOError("RX payload must not be empty.")

        if not self._connected_flag:
            raise StreamIOError("Cannot inject RX while stream is disconnected.")

        self._rx_queue.put(payload)
        return True

    def read_tx(self, timeout: Optional[float] = None) -> Optional[bytes]:
        """Read one chunk from the TX queue."""
        try:
            return self._tx_queue.get(timeout=timeout)
        except Empty:
            return None
        except Exception as exc:
            raise StreamIOError("Failed to read from emulator TX queue.") from exc

    def clear_queues(self) -> None:
        """Clear RX and TX queues."""
        self._drain_queue(self._rx_queue)
        self._drain_queue(self._tx_queue)

    def get_opened_port(self) -> Optional[str]:
        """Return current opened endpoint name."""
        return self._opened_port

    def _on_connected(self) -> None:
        """Publish connected event."""
        self.publish(StreamEvent.CONNECTED)

    def _on_disconnected(self) -> None:
        """Publish disconnected event."""
        self.publish(StreamEvent.DISCONNECTED)

    @staticmethod
    def _drain_queue(queue: Queue[bytes]) -> None:
        """Drain all items from a queue."""
        while True:
            try:
                queue.get_nowait()
            except Empty:
                break
