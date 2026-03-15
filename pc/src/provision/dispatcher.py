"""Provision dispatcher interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from stream.base import Stream


class ProvisionDispatcher(ABC):
    """Abstract base for provisioning dispatchers."""

    def __init__(self, stream: Stream) -> None:
        """Initialize dispatcher with a stream instance."""
        self._stream = stream

    @property
    def stream(self) -> Stream:
        """Return the underlying stream."""
        return self._stream

    @abstractmethod
    def dispatch(self, factory_data: dict[str, Any]) -> bool:
        """Dispatch one factory data payload. Returns True on success."""
        raise NotImplementedError
