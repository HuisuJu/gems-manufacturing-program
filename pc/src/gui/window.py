from __future__ import annotations

import sys

from traceback import format_exception

from typing import Callable

import tkinter as tk

import customtkinter as ctk

from logger import Logger, LogLevel

from system import ModelName

from .startup_dialog import StartupSelectionDialog


PageFactory = Callable[[ctk.CTkFrame], ctk.CTkFrame]


class Window(ctk.CTk):
    """
    Main application window.

    Startup flow:
        1. Create hidden root window.
        2. Show startup selection dialog.
        3. If confirmed, initialize tabs/pages.
        4. Show main window.

    Notes:
        - The startup dialog is responsible for storing MODEL_NAME into the
          global settings module.
        - Page instances are exposed through self.pages.
    """

    def __init__(self, page_factories: list[tuple[PageFactory, str]]):
        super().__init__()

        self.title("Hyundai HT GEMS Factory Provisioning Tool")
        self.selected_model_name: ModelName | None = None
        self.pages: dict[str, ctk.CTkFrame] = {}

        self.withdraw()

        selected_model_name = self._show_startup_selection_dialog()
        if selected_model_name is None:
            return

        self.selected_model_name = selected_model_name

        self._initialize_main_layout(page_factories)

        self._show_main_window_safely()

    def _show_startup_selection_dialog(self) -> ModelName | None:
        """
        Show the startup selection dialog before building the main UI.
        """
        dialog = StartupSelectionDialog(self)
        return dialog.show_modal()

    def _initialize_main_layout(
        self,
        page_factories: list[tuple[PageFactory, str]],
    ) -> None:
        """
        Build the main window layout and page tabs.
        """
        # Keep deterministic fallback size first. Maximize is applied after the
        # window becomes visible to avoid platform-specific show timing issues.
        self.geometry("1280x800")

        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self._tabview = ctk.CTkTabview(self)
        self._tabview.grid(row=0, column=0, padx=20, pady=(0, 20), sticky="nsew")

        for page_factory, page_name in page_factories:
            tab = self._tabview.add(page_name)
            tab.grid_rowconfigure(0, weight=1)
            tab.grid_columnconfigure(0, weight=1)

            page = page_factory(tab)
            page.grid(row=0, column=0, sticky="nsew")
            self.pages[page_name] = page

    def _show_main_window_safely(self) -> None:
        """
        Show the main window with retries to avoid hidden-window states.

        On Windows, withdrawn + modal + immediate maximize can leave the root
        hidden while Tk mainloop is still running.
        """
        for _ in range(3):
            try:
                self.deiconify()
                self.lift()
                self.update_idletasks()
            except tk.TclError as exc:
                Logger.write(
                    LogLevel.ALERT,
                    "Failed to show main window (deiconify/lift). "
                    f"({type(exc).__name__}: {exc})",
                )
                continue

            if self.winfo_viewable():
                break

        self._apply_initial_window_state()

        try:
            self.focus_force()
        except tk.TclError:
            pass

    def _apply_initial_window_state(self) -> None:
        """
        Apply maximize behavior after the root window is visible.

        Tk window-state application timing can vary per platform/window manager,
        so we apply maximize now and retry shortly after mapping.
        """
        self._maximize_window(log_failure=True)
        self.after(80, self._maximize_window)
        self.after(250, self._maximize_window)

    def _maximize_window(self, log_failure: bool = False) -> None:
        """
        Try multiple maximize strategies with a screen-size fallback.
        """
        if sys.platform.startswith("win"):
            attempts = [
                ("state(zoomed)", lambda: self.state("zoomed")),
            ]
        elif sys.platform == "darwin":
            attempts = [
                ("state(zoomed)", lambda: self.state("zoomed")),
            ]
        else:
            attempts = [
                (
                    "wm_attributes(-zoomed)",
                    lambda: self.wm_attributes("-zoomed", True),
                ),
                ("attributes(-zoomed)", lambda: self.attributes("-zoomed", True)),
                ("state(zoomed)", lambda: self.state("zoomed")),
            ]

        last_error: Exception | None = None
        maximize_call_succeeded = False
        for _, operation in attempts:
            try:
                operation()
                maximize_call_succeeded = True
            except Exception as exc:
                last_error = exc

        try:
            self.update_idletasks()
            screen_width = self.winfo_screenwidth()
            screen_height = self.winfo_screenheight()
            width = max(self.winfo_width(), 1)
            height = max(self.winfo_height(), 1)

            # If maximize state was ignored by the WM, fallback to screen-sized
            # geometry so the app still opens effectively maximized.
            if width < int(screen_width * 0.9) or height < int(screen_height * 0.9):
                self.geometry(f"{screen_width}x{screen_height}+0+0")
                maximize_call_succeeded = True
        except Exception as exc:
            last_error = exc

        if log_failure and not maximize_call_succeeded and last_error is not None:
            Logger.write(
                LogLevel.ALERT,
                "Failed to apply maximized window state. "
                f"({type(last_error).__name__}: {last_error})",
            )

    def report_callback_exception(self, exc, val, tb) -> None:
        """
        Handle uncaught Tk callback exceptions.
        """
        traceback_text = "".join(format_exception(exc, val, tb))
        message = (
            "Tk callback exception occurred. "
            "UI may become unstable.\n"
            f"{traceback_text}"
        )

        try:
            Logger.write(LogLevel.ALERT, message)
        except Exception:
            pass

        try:
            print(message, file=sys.stderr, flush=True)
        except Exception:
            pass
