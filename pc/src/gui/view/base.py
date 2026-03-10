from __future__ import annotations

from typing import Callable, Optional

import customtkinter as ctk


class ViewError(Exception):
    """
    Base exception for view failures.
    """


class ViewConfigurationError(ViewError):
    """
    Raised when the view is configured incorrectly.
    """


ViewHandler = Callable[[], None]


class View(ctk.CTkFrame):
    """
    Base class for UI views.

    A view owns a mapping from event name to handler. When trigger() is called,
    the matching handler is scheduled on the UI thread through after(0, ...).

    Child classes are expected to populate self._event_handlers.
    """

    def __init__(self, parent: ctk.CTkFrame, **kwargs) -> None:
        """
        Initialize the base view.

        Args:
            parent:
                Parent widget.
            **kwargs:
                Additional CTkFrame keyword arguments.
        """
        super().__init__(parent, fg_color="transparent", **kwargs)
        self._event_handlers: dict[str, ViewHandler] = {}

    def trigger(self, event_name: str) -> None:
        """
        Trigger one registered view event.

        The matching handler is scheduled through after(0, ...), so this method
        can be called safely from a background thread as long as the UI toolkit
        permits after() scheduling from that thread.

        Args:
            event_name:
                Registered event name.

        Raises:
            ViewConfigurationError:
                The event name is invalid or no handler is registered.
        """
        normalized_name = self._normalize_event_name(event_name)
        handler = self._event_handlers.get(normalized_name)

        if handler is None:
            raise ViewConfigurationError(
                f"No handler is registered for view event '{normalized_name}'."
            )

        self.after(0, handler)

    def has_event(self, event_name: str) -> bool:
        """
        Return whether the view has a handler for the given event.

        Args:
            event_name:
                Event name to check.

        Returns:
            True if the event is registered, otherwise False.
        """
        normalized_name = self._normalize_event_name(event_name)
        return normalized_name in self._event_handlers

    def set_event_handler(self, event_name: str, handler: Optional[ViewHandler]) -> None:
        """
        Register, replace, or remove one event handler.

        Args:
            event_name:
                Event name.
            handler:
                Handler to register. If None, the handler is removed.

        Raises:
            ViewConfigurationError:
                The event name or handler is invalid.
        """
        normalized_name = self._normalize_event_name(event_name)

        if handler is None:
            self._event_handlers.pop(normalized_name, None)
            return

        if not callable(handler):
            raise ViewConfigurationError(
                f"The handler for view event '{normalized_name}' is not callable."
            )

        self._event_handlers[normalized_name] = handler

    def _normalize_event_name(self, event_name: str) -> str:
        """
        Normalize and validate an event name.

        Args:
            event_name:
                Raw event name.

        Returns:
            Normalized event name.

        Raises:
            ViewConfigurationError:
                The event name is invalid.
        """
        if not isinstance(event_name, str):
            raise ViewConfigurationError("The view event name must be a string.")

        normalized_name = event_name.strip()
        if not normalized_name:
            raise ViewConfigurationError("The view event name must not be empty.")

        return normalized_name