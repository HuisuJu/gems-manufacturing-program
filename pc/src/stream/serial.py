"""Serial stream implementation."""

from __future__ import annotations

import threading
import time
from queue import Empty, Queue
from typing import Optional

import serial
import serial.threaded
import serial.tools.list_ports

from .base import (
    Stream,
    StreamEvent,
    StreamIOError,
)


class SerialStream(Stream):
    """Thread-safe serial byte stream based on pySerial ReaderThread."""

    _lock: threading.Lock
    _serial_port: Optional[serial.Serial]
    _reader_thread: Optional[serial.threaded.ReaderThread]
    _reader_queue: Queue[bytes]
    _reader_buffer: bytearray
    _protocol: Optional["SerialStream._Protocol"]
    _is_connected: bool

    class _Protocol(serial.threaded.Protocol):
        """pySerial protocol bridge for SerialStream."""

        _owner: "SerialStream"

        def __init__(self, owner: "SerialStream") -> None:
            self._owner = owner

        def data_received(self, data: bytes) -> None:
            if data:
                self._owner._reader_queue.put(data)

        def connection_made(self, transport: serial.threaded.ReaderThread) -> None:
            _ = transport
            with self._owner._lock:
                self._owner._is_connected = True

            self._owner.publish(StreamEvent.CONNECTED)

        def connection_lost(self, exc: Optional[Exception]) -> None:
            _ = exc
            with self._owner._lock:
                self._owner._is_connected = False

            self._owner.publish(StreamEvent.DISCONNECTED)

    def __init__(self) -> None:
        """Initialize stream state."""
        super().__init__()
        self._lock = threading.Lock()

        self._reader_thread: Optional[serial.threaded.ReaderThread] = None
        self._reader_queue: Queue[bytes] = Queue()
        self._reader_buffer = bytearray()
        self._protocol: Optional[SerialStream._Protocol] = None

        self._serial_port: Optional[serial.Serial] = None
        self._is_connected = False

    @staticmethod
    def list_ports() -> list[str]:
        """Return available serial device names."""
        return [port.device for port in serial.tools.list_ports.comports()]

    def is_connected(self) -> bool:
        """Return whether the stream is connected."""
        with self._lock:
            serial_port = self._serial_port
            reader_thread = self._reader_thread
            is_connected = self._is_connected

        return (
            serial_port is not None
            and serial_port.is_open
            and reader_thread is not None
            and reader_thread.is_alive()
            and is_connected
        )

    def open(self, port: str, baudrate: int = 115200) -> bool:
        """Open a serial port and start the reader thread."""
        if (
            self.is_connected()
            and self._serial_port.port == port
            and self._serial_port.baudrate == baudrate
        ):
            return True
        else:
            self.close()

        try:
            serial_port = serial.Serial(
                port=port,
                baudrate=baudrate,
                timeout=1.0,
                write_timeout=1.0,
            )

            reader_thread = serial.threaded.ReaderThread(
                serial_port,
                lambda: SerialStream._Protocol(self),
            )
            reader_thread.start()

            _transport, protocol = reader_thread.connect()

            with self._lock:
                self._serial_port = serial_port
                self._reader_thread = reader_thread
                self._protocol = protocol
                self._is_connected = True

            return True

        except Exception as exc:
            try:
                self.close()
            except Exception:
                pass

            raise StreamIOError(
                f"Failed to open serial port '{port}' at baudrate {baudrate}."
            ) from exc

    def close(self) -> None:
        """Close the stream and stop the reader thread."""
        with self._lock:
            reader_thread = self._reader_thread
            serial_port = self._serial_port

            self._reader_thread = None
            self._protocol = None
            self._serial_port = None
            self._is_connected = False

        close_error: Optional[Exception] = None

        if reader_thread is not None:
            try:
                reader_thread.close()
            except Exception as exc:
                close_error = exc
        if serial_port is not None and serial_port.is_open:
            try:
                serial_port.close()
            except Exception as exc:
                close_error = exc

        if close_error is not None:
            raise StreamIOError("Failed to close serial port.") from close_error

    def write(self, data: bytes) -> bool:
        """Write bytes to the stream."""
        if data is None or not isinstance(data, (bytes, bytearray, memoryview)):
            return False
        if self.is_connected() is False:
            return False

        try:
            self._reader_thread.write(data)
            return True
        except Exception as exc:
            raise StreamIOError("Failed to write bytes to serial port.") from exc

    def read(self, size: int, timeout: Optional[float] = None) -> Optional[bytes]:
        """Read up to size bytes from RX queue within timeout."""
        if size <= 0:
            return None
        if self.is_connected() is False:
            return None

        result = bytearray()

        buffered_size = min(size, len(self._reader_buffer))
        result.extend(self._reader_buffer[:buffered_size])
        del self._reader_buffer[:buffered_size]

        deadline: Optional[float]
        if timeout is None:
            deadline = None
        else:
            deadline = time.monotonic() + timeout

        single_poll: bool = timeout is not None and timeout <= 0.0

        try:
            while len(result) < size:
                if deadline is None:
                    wait_timeout = None
                else:
                    wait_timeout = max(deadline - time.monotonic(), 0.0)

                if wait_timeout is not None and wait_timeout <= 0.0 and not single_poll:
                    break
                
                single_poll = False

                chunk = self._reader_queue.get(timeout=wait_timeout)

                more_size = size - len(result)
                result.extend(chunk[:more_size])

                if len(chunk) > more_size:
                    self._reader_buffer.extend(chunk[more_size:])

            return bytes(result) if result else None

        except Empty:
            return bytes(result) if result else None

        except Exception as exc:
            raise StreamIOError("Failed to read from serial queue.") from exc
