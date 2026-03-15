from __future__ import annotations

from collections.abc import Callable
from tkinter import TclError
from typing import Optional

import customtkinter as ctk

from logger import Logger, LogLevel
from view.common.navigation.navigator import Navigator

from .step_matter_credentials import MatterCredentialsStep
from .step_model import ModelSelectionStep
from .step_station import StationSetupStep


StartUpClosedCallback = Callable[[bool], None]


class StartUpController(ctk.CTkToplevel):
    """Startup controller dialog."""

    _WINDOW_WIDTH = 600
    _WINDOW_HEIGHT = 700

    # Navigator outer margin
    _CONTENT_PADX = 28
    _CONTENT_PADY = 24

    def __init__(
        self,
        parent: ctk.CTk,
        on_closed: Optional[StartUpClosedCallback] = None,
    ) -> None:
        super().__init__(parent)

        self._on_closed = on_closed
        self._closed = False

        self.title("Initial Configuration")
        self.resizable(False, False)

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        try:
            self.grab_set()
        except TclError as exc:
            Logger.write(
                LogLevel.ALERT,
                "Startup controller could not acquire modal grab. "
                f"reason='{type(exc).__name__}: {exc}'",
            )

        self._build_layout()
        self._bind_events()
        self._show_centered()

    def _build_layout(self) -> None:
        """Build startup dialog layout."""
        self._navigator = Navigator(
            self,
            steps=[
                ModelSelectionStep,
                StationSetupStep,
                MatterCredentialsStep,
            ],
            on_finished=self._on_finished,
        )

        self._navigator.grid(
            row=0,
            column=0,
            sticky="nsew",
            padx=self._CONTENT_PADX,
            pady=self._CONTENT_PADY,
        )

    def _bind_events(self) -> None:
        """Bind window-level events."""
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _on_finished(self) -> None:
        """Handle successful completion."""
        self._close(True)

    def _on_close(self) -> None:
        """Close without completing startup."""
        self._close(False)

    def _close(self, is_success: bool) -> None:
        """Release modal state, destroy the dialog, and notify once."""
        if self._closed:
            return

        self._closed = True

        try:
            self.grab_release()
        except TclError:
            pass

        callback = self._on_closed

        try:
            self.destroy()
        except TclError:
            pass

        if callback is not None:
            callback(is_success)

    def _show_centered(self) -> None:
        """Center the dialog and bring it to the front."""
        self.update_idletasks()

        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()

        width = self._WINDOW_WIDTH
        height = self._WINDOW_HEIGHT

        x = (screen_width - width) // 2
        y = (screen_height - height) // 2

        self.geometry(f"{width}x{height}+{x}+{y}")

        try:
            self.deiconify()
            self.lift()
        except TclError as exc:
            Logger.write(
                LogLevel.ALERT,
                "Startup controller could not be shown in front. "
                f"reason='{type(exc).__name__}: {exc}'",
            )

        try:
            self.attributes("-topmost", True)
        except TclError:
            pass

        try:
            self.focus_force()
        except TclError:
            pass

        self.after(
            50,
            lambda: (
                self.winfo_exists()
                and self.attributes("-topmost", False)
            ),
        )
