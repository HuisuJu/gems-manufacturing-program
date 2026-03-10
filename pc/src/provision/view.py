from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Callable, Optional

from provision.manager import ProvisionManagerEvent, ProvisionState


class WorkerIndicatorState(str, Enum):
    """
    Visual worker state shown by the provisioning view.
    """

    IDLE = "IDLE"
    READY = "READY"
    PROGRESS = "PROGRESS"
    SUCCESS = "SUCCESS"
    FAIL = "FAIL"


@dataclass(slots=True)
class ProvisioningUserEvent:
    """
    User action emitted by the provisioning view.
    """

    name: str
    message: str


ProvisioningUserEventListener = Callable[[ProvisioningUserEvent], None]


class ProvisioningView(ABC):
    """
    Abstract interface for the provisioning view.

    A concrete UI widget should implement this interface so that the provision
    manager can drive view updates without depending on a specific UI toolkit.
    """

    @abstractmethod
    def apply_manager_event(self, event: ProvisionManagerEvent) -> None:
        """
        Apply one ProvisionManagerEvent to the view.

        Args:
            event:
                Latest event emitted by ProvisionManager.
        """
        raise NotImplementedError

    @abstractmethod
    def set_worker_indicator_state(self, state: WorkerIndicatorState) -> None:
        """
        Update the worker indicator visual state.

        Args:
            state:
                Visual worker state to show.
        """
        raise NotImplementedError

    @abstractmethod
    def set_status_message(self, text: str) -> None:
        """
        Update the main status message.

        Args:
            text:
                Human-readable status text.
        """
        raise NotImplementedError

    @abstractmethod
    def set_next_instruction(self, text: str) -> None:
        """
        Update the next-action instruction text.

        Args:
            text:
                Human-readable next instruction.
        """
        raise NotImplementedError

    @abstractmethod
    def set_dispatcher_status(self, is_ready: bool) -> None:
        """
        Update the dispatcher readiness display.

        Args:
            is_ready:
                True if the dispatcher is ready, otherwise False.
        """
        raise NotImplementedError

    @abstractmethod
    def set_primary_button(self, text: str, enabled: bool) -> None:
        """
        Update the primary action button state.

        Args:
            text:
                Button text.
            enabled:
                Whether the button is enabled.
        """
        raise NotImplementedError

    @abstractmethod
    def set_user_event_listener(
        self,
        listener: Optional[ProvisioningUserEventListener],
    ) -> None:
        """
        Register a listener for user actions emitted by the view.

        Args:
            listener:
                Listener to receive user events, or None to clear it.
        """
        raise NotImplementedError