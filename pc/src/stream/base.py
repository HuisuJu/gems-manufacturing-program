"""Abstract byte stream interface.

This module defines the common stream contract used by serial and emulator
transports. Concrete implementations are responsible only for carrying raw
bytes and exposing a uniform connection lifecycle API.

Protocol framing, message parsing, retransmission, and transport-specific
application logic must be implemented in upper layers.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Callable, Optional


StreamEventListener = Callable[[str], None]


class Stream(ABC):
    """Abstract raw byte stream interface.

    Implementations may wrap serial ports, in-memory emulators, sockets, or
    other transports, as long as they expose the same connection and I/O API.

    Event listeners receive event names such as:
        - ``"connected"``
        - ``"disconnected"``
    """

    @staticmethod
    @abstractmethod
    def list_ports() -> list[str]:
        """Return available stream endpoints.

        For serial-based implementations, this usually returns serial device
        names. For non-serial implementations, this may return virtual endpoint
        names or an empty list.

        Returns:
            Available endpoint names.
        """
        raise NotImplementedError

    @abstractmethod
    def subscribe_event(self, listener: StreamEventListener) -> None:
        """Register a stream state listener.

        Args:
            listener:
                Callback invoked on stream events.
        """
        raise NotImplementedError

    @abstractmethod
    def unsubscribe_event(self, listener: StreamEventListener) -> None:
        """Unregister a previously registered stream state listener.

        Args:
            listener:
                Callback to remove.
        """
        raise NotImplementedError

    @abstractmethod
    def is_connected(self) -> bool:
        """Return the current connection status.

        Returns:
            True if the stream is connected, otherwise False.
        """
        raise NotImplementedError

    @abstractmethod
    def open(self, port: str, baudrate: int = 115200) -> bool:
        """Open the stream endpoint.

        Args:
            port:
                Endpoint name or identifier.
            baudrate:
                Endpoint speed when applicable.

        Returns:
            True on success, otherwise False.
        """
        raise NotImplementedError

    @abstractmethod
    def close(self) -> None:
        """Close the stream endpoint."""
        raise NotImplementedError

    @abstractmethod
    def write(self, data: bytes) -> bool:
        """Write raw bytes to the stream.

        Args:
            data:
                Raw byte sequence to send.

        Returns:
            True on success, otherwise False.
        """
        raise NotImplementedError

    @abstractmethod
    def read(self, timeout: Optional[float] = None) -> Optional[bytes]:
        """Read one raw byte chunk from the stream.

        Args:
            timeout:
                Maximum wait time in seconds. None means implementation-defined
                behavior.

        Returns:
            One raw byte chunk if available, otherwise None.
        """
        raise NotImplementedError

    @abstractmethod
    def publish(self, name: str) -> None:
        """Publish one stream event to subscribed listeners.

        Args:
            name:
                Event name.
        """
        raise NotImplementedError