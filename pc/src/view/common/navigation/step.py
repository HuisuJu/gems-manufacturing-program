from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable

import customtkinter as ctk


ReadyCallback = Callable[[bool], None]


class NavigationStep(ctk.CTkFrame, ABC):
    """Abstract base class for one navigable step."""

    def __init__(
        self,
        parent: ctk.CTkFrame,
        on_ready: ReadyCallback | None = None,
        **kwargs,
    ) -> None:
        super().__init__(parent, fg_color="transparent", **kwargs)

        self._on_ready = on_ready
        self._is_ready = False

    @property
    def is_ready(self) -> bool:
        """Return whether this step is ready to proceed."""
        return self._is_ready

    @is_ready.setter
    def is_ready(self, value: bool) -> None:
        """Update ready state and notify listener when it changes."""
        ready = bool(value)
        if self._is_ready == ready:
            return

        self._is_ready = ready

        if self._on_ready is not None:
            self._on_ready(self._is_ready)

    @abstractmethod
    def commit(self) -> bool:
        """Validate and persist this step before moving forward."""
        raise NotImplementedError
