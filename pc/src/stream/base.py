"""Shared interface for raw byte streams."""

from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum
import threading
from typing import Callable, Optional


class StreamError(Exception):
    """Base exception for stream operations."""


class StreamIOError(StreamError):
    """Raised when stream open/read/write/close fails."""


class StreamEventError(StreamError):
    """Raised when notifying stream listeners fails."""


class StreamEvent(Enum):
    """Connection events."""

    CONNECTED = 1
    DISCONNECTED = 2


StreamEventListener = Callable[[StreamEvent], None]


class Stream(ABC):
    """Base interface for stream implementations."""

    _registry_lock = threading.RLock()
    _instance: Optional["Stream"] = None

    def __init__(self) -> None:
        """Initialize shared event listener state."""
        self._event_lock = threading.RLock()
        self._event_listeners: list[StreamEventListener] = []

    @classmethod
    def set_delegate(cls, stream: "Stream") -> None:
        """Register the shared stream instance."""
        with Stream._registry_lock:
            Stream._instance = stream

    @classmethod
    def get_delegate(cls) -> Optional["Stream"]:
        """Return the shared stream instance."""
        with Stream._registry_lock:
            stream = Stream._instance

        return stream

    @staticmethod
    @abstractmethod
    def list_ports() -> list[str]:
        """Return available endpoint names."""
        raise NotImplementedError

    def subscribe_event(self, listener: StreamEventListener) -> None:
        """Register an event listener."""
        with self._event_lock:
            if listener not in self._event_listeners:
                self._event_listeners.append(listener)

    def unsubscribe_event(self, listener: StreamEventListener) -> None:
        """Remove an event listener."""
        with self._event_lock:
            if listener in self._event_listeners:
                self._event_listeners.remove(listener)

    @abstractmethod
    def is_connected(self) -> bool:
        """Return whether the stream is connected."""
        raise NotImplementedError

    @abstractmethod
    def open(self, port: str, baudrate: int = 115200) -> bool:
        """Open the stream endpoint."""
        raise NotImplementedError

    @abstractmethod
    def close(self) -> None:
        """Close the stream."""
        raise NotImplementedError

    @abstractmethod
    def read(self, size: int, timeout: Optional[float] = None) -> Optional[bytes]:
        """Read exactly size bytes within timeout, or return None."""
        raise NotImplementedError

    @abstractmethod
    def write(self, data: bytes) -> bool:
        """Write bytes to the stream."""
        raise NotImplementedError

    def publish(self, event: StreamEvent) -> None:
        """Notify listeners about a stream event."""
        with self._event_lock:
            listeners = list(self._event_listeners)

        for listener in listeners:
            try:
                listener(event)
            except Exception as exc:
                raise StreamEventError("Stream listener failed.") from exc
