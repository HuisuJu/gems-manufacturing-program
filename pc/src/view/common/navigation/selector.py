from __future__ import annotations

from collections.abc import Callable
from enum import Enum

import customtkinter as ctk


class NavigationSelectType(str, Enum):
    """Navigation button types."""

    PREV = "Prev"
    NEXT = "Next"
    FINISH = "Finish"


NavigationClickedCallback = Callable[[NavigationSelectType], None]


class NavigationSelector(ctk.CTkFrame):
    """Navigation button bar for multi-step flows."""

    def __init__(
        self,
        parent: ctk.CTkFrame | ctk.CTkToplevel,
        on_clicked: NavigationClickedCallback | None = None,
        **kwargs,
    ) -> None:
        super().__init__(parent, fg_color="transparent", **kwargs)

        self._on_clicked = on_clicked

        self._left_type: NavigationSelectType | None = None
        self._right_type: NavigationSelectType | None = None

        self._left_button = ctk.CTkButton(
            self,
            text="",
            width=110,
            height=42,
            command=self._on_left_clicked,
        )
        self._left_button.grid(row=0, column=0, padx=(0, 8), pady=0)

        self._right_button = ctk.CTkButton(
            self,
            text="",
            width=110,
            height=42,
            command=self._on_right_clicked,
        )
        self._right_button.grid(row=0, column=1, padx=0, pady=0)

        self.invalidate(None, None)

    def invalidate(
        self,
        left: NavigationSelectType | None,
        right: NavigationSelectType | None,
    ) -> None:
        """Update button types and visibility."""
        self._left_type = left
        self._right_type = right

        if left is None:
            self._left_button.grid_remove()
        else:
            self._left_button.configure(text=left.value)
            self._left_button.grid()

        if right is None:
            self._right_button.grid_remove()
        else:
            self._right_button.configure(text=right.value)
            self._right_button.grid()

    def _on_left_clicked(self) -> None:
        """Handle left button click."""
        if self._left_type is None:
            return

        if self._on_clicked is not None:
            self._on_clicked(self._left_type)

    def _on_right_clicked(self) -> None:
        """Handle right button click."""
        if self._right_type is None:
            return

        if self._on_clicked is not None:
            self._on_clicked(self._right_type)
