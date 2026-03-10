from __future__ import annotations

import tkinter as tk
from threading import RLock
from typing import Callable, Mapping


class ViewError(Exception):
    """
    Base exception for view failures.
    """


class ViewConfigurationError(ViewError):
    """
    Raised when the view is configured incorrectly.
    """


ViewCallback = Callable[[], None]


class View:
    """
    Minimal tkinter-aware callback dispatcher.

    A View instance holds a mapping from string keys to callbacks. When
    trigger(key) is called, the corresponding callback is scheduled on the UI
    thread through window.after(0, callback).

    This allows background model/service code to request UI actions without
    directly touching UI widgets from a non-UI thread.
    """

    def __init__(
        self,
        window: tk.Misc,
        callbacks: Mapping[str, ViewCallback] | None = None,
    ) -> None:
        """
        Initialize the view.

        Args:
            window:
                Tkinter/customtkinter root or widget exposing after().
            callbacks:
                Optional initial mapping from key to callback.
        """
        self._window = window
        self._callbacks: dict[str, ViewCallback] = {}
        self._lock = RLock()

        if callbacks is not None:
            for key, callback in callbacks.items():
                self.set_callback(key, callback)

    def set_callback(self, key: str, callback: ViewCallback) -> None:
        """
        Register or replace a callback for a key.

        Args:
            key:
                Callback key.
            callback:
                Callback to run when the key is triggered.

        Raises:
            ViewConfigurationError:
                The key or callback is invalid.
        """
        normalized_key = self._normalize_key(key)

        if not callable(callback):
            raise ViewConfigurationError(
                f"The callback for '{normalized_key}' is not callable."
            )

        with self._lock:
            self._callbacks[normalized_key] = callback

    def remove_callback(self, key: str) -> None:
        """
        Remove a callback for a key.

        Args:
            key:
                Callback key.
        """
        normalized_key = self._normalize_key(key)

        with self._lock:
            self._callbacks.pop(normalized_key, None)

    def has_callback(self, key: str) -> bool:
        """
        Return whether a callback exists for the given key.

        Args:
            key:
                Callback key.

        Returns:
            True if the callback is registered, otherwise False.
        """
        normalized_key = self._normalize_key(key)

        with self._lock:
            return normalized_key in self._callbacks

    def trigger(self, key: str) -> None:
        """
        Schedule the callback associated with the given key on the UI thread.

        Args:
            key:
                Callback key.

        Raises:
            ViewConfigurationError:
                The key is invalid or no callback is registered for it.
        """
        normalized_key = self._normalize_key(key)

        with self._lock:
            callback = self._callbacks.get(normalized_key)

        if callback is None:
            raise ViewConfigurationError(
                f"No callback is registered for view key '{normalized_key}'."
            )

        self._window.after(0, callback)

    def _normalize_key(self, key: str) -> str:
        """
        Normalize and validate a callback key.

        Args:
            key:
                Callback key.

        Returns:
            Normalized key string.

        Raises:
            ViewConfigurationError:
                The key is invalid.
        """
        if not isinstance(key, str):
            raise ViewConfigurationError("The view key must be a string.")

        normalized = key.strip()
        if not normalized:
            raise ViewConfigurationError("The view key must not be empty.")

        return normalized