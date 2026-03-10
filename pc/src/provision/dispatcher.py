"""
Provision dispatcher interface.

A dispatcher is responsible for delivering one complete factory data payload to
a target device or emulator. The dispatcher does not know where the payload
came from and does not own provisioning workflow state.

Expected usage:
    - ProvisionManager constructs the dispatcher with a readiness callback
    - ProvisionManager checks readiness
    - ProvisionManager calls dispatch(factory_data)
    - Dispatcher returns a DispatchResult synchronously
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Callable, Optional


ReadyListener = Callable[[bool], None]


@dataclass(frozen=True, slots=True)
class DispatchResult:
    """
    Result returned by a dispatcher after one provisioning attempt.

    Attributes:
        success:
            True when provisioning completed successfully.
        message:
            Human-readable summary suitable for UI display and reporting.
        details:
            Optional implementation-specific diagnostic details.
    """

    success: bool
    message: str
    details: Optional[dict[str, Any]] = None


class ProvisionDispatcher(ABC):
    """
    Abstract interface for provisioning dispatchers.

    A dispatcher implementation is responsible for pushing one factory data
    payload to one target and waiting until the attempt completes or fails.

    Notes:
        - dispatch() must be synchronous and blocking.
        - Implementations should use the readiness callback to notify the
          manager when the target becomes ready or unavailable.
        - The factory_data object must be treated as an opaque dictionary by
          the interface. Concrete implementations may interpret its full
          content as needed.
    """

    def __init__(self, ready_listener: ReadyListener | None = None) -> None:
        """
        Initialize dispatcher base state.

        Args:
            ready_listener:
                Callback invoked when dispatcher readiness changes.
        """
        self._ready_listener = ready_listener

    def notify_ready_changed(self, is_ready: bool) -> None:
        """
        Notify the registered listener that readiness has changed.

        Concrete implementations should call this method whenever their ready
        state changes, for example when a serial port is connected or lost.

        Args:
            is_ready:
                Current dispatcher readiness state.
        """
        if self._ready_listener is not None:
            self._ready_listener(is_ready)

    @abstractmethod
    def is_ready(self) -> bool:
        """
        Return whether the dispatcher is currently ready to provision.

        Returns:
            True if dispatch() can be attempted now, otherwise False.
        """
        raise NotImplementedError

    @abstractmethod
    def dispatch(self, factory_data: dict[str, Any]) -> DispatchResult:
        """
        Deliver one complete factory data payload to the target.

        This method must block until the provisioning attempt has completed or
        failed.

        Args:
            factory_data:
                Complete factory data supplied by FactoryDataProvider.

        Returns:
            DispatchResult describing the outcome.

        Raises:
            Exception:
                Concrete implementations may raise an exception for unexpected
                transport or internal failures. ProvisionManager should convert
                such failures into a failed provisioning result.
        """
        raise NotImplementedError
