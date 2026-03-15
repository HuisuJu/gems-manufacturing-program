from __future__ import annotations

import sys
from traceback import format_exception
from tkinter import TclError

import customtkinter as ctk

from logger import Logger, LogLevel
from provision import ProvisionManager
from system import MODEL_NAME_KEY, ModelName, Settings

from .frame import ProvisioningFrame
from .startup import StartUpController
from .widget import ProvisioningUserEvent


class BaseTab(ctk.CTkTabview):
    """Base tab layout shared by all models for now."""

    _FRAME_SPECS: tuple[tuple[type[ctk.CTkFrame], str], ...] = (
        (ProvisioningFrame, "Provisioning"),
    )

    def __init__(self, parent: ctk.CTk, **kwargs) -> None:
        super().__init__(parent, **kwargs)

        self.frames: dict[str, ctk.CTkFrame] = {}
        self._build_tabs()

    def _build_tabs(self) -> None:
        """Create tab pages and their root frames."""
        for frame_class, frame_name in self._FRAME_SPECS:
            tab = self.add(frame_name)
            tab.grid_rowconfigure(0, weight=1)
            tab.grid_columnconfigure(0, weight=1)

            frame = frame_class(tab)
            frame.grid(row=0, column=0, sticky="nsew")

            self.frames[frame_name] = frame


DoorlockTab = BaseTab
ThermostatTab = BaseTab
EmulatorTab = BaseTab


class Window(ctk.CTk):
    """Main application window."""

    _TITLE = "Hyundai HT GEMS Factory Provisioning Tool"

    _DEFAULT_WIDTH = 1280
    _DEFAULT_HEIGHT = 800

    _CONTENT_PADX = 20
    _CONTENT_PADY_TOP = 0
    _CONTENT_PADY_BOTTOM = 20

    def __init__(self) -> None:
        super().__init__()

        self._tab: BaseTab | None = None
        self._startup_controller: StartUpController | None = None

        self.title(self._TITLE)

        # Keep the window hidden until startup finishes and the main UI is ready.
        self.withdraw()

        self._startup_controller = StartUpController(
            self,
            on_closed=self._on_startup_finished,
        )

    def _on_startup_finished(self, is_success: bool) -> None:
        """Handle startup dialog completion."""
        self._startup_controller = None

        if not is_success:
            self.destroy()
            return

        try:
            self._build_ui()
            self._prepare_window_before_show()
            self._show_window()
        except Exception as exc:
            Logger.write(
                LogLevel.ALERT,
                "Failed to initialize main window. "
                f"({type(exc).__name__}: {exc})",
            )
            self.destroy()

    def _build_ui(self) -> None:
        """Build the main window layout."""
        self.geometry(f"{self._DEFAULT_WIDTH}x{self._DEFAULT_HEIGHT}")

        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        model = self._resolve_model()
        self._tab = self._create_tab_for_model(model)

        self._tab.grid(
            row=0,
            column=0,
            padx=self._CONTENT_PADX,
            pady=(self._CONTENT_PADY_TOP, self._CONTENT_PADY_BOTTOM),
            sticky="nsew",
        )

        self._wire_provisioning_integration()

    def _wire_provisioning_integration(self) -> None:
        """Connect ProvisionManager with ProvisionerWidget interactions."""
        if self._tab is None:
            return

        frame = self._tab.frames.get("Provisioning")
        if not isinstance(frame, ProvisioningFrame):
            return

        frame.provisioning_view.bind_manager_event_listener(ProvisionManager)
        frame.provisioning_view.set_user_event_listener(
            lambda event: self._on_provisioning_user_event(frame, event)
        )

    def _on_provisioning_user_event(
        self,
        frame: ProvisioningFrame,
        event: ProvisioningUserEvent,
    ) -> None:
        """Handle start/finish actions emitted by ProvisionerWidget."""
        if event.action == "start":
            ProvisionManager.start()
            return

        if event.action == "finish":
            ProvisionManager.finish()
            frame.log_settings_view.handle_finish()

    def _resolve_model(self) -> ModelName:
        """Read and validate the configured model."""
        raw_model = Settings.get(MODEL_NAME_KEY)

        if isinstance(raw_model, ModelName):
            return raw_model

        if isinstance(raw_model, str) and raw_model:
            try:
                return ModelName(raw_model)
            except ValueError as exc:
                raise ValueError(f"Invalid model value: {raw_model!r}") from exc

        raise ValueError(f"Invalid model value: {raw_model!r}")

    def _create_tab_for_model(self, model: ModelName) -> BaseTab:
        """Create the root tab widget for the selected model."""
        match model:
            case ModelName.DOORLOCK:
                return DoorlockTab(self)
            case ModelName.THERMOSTAT:
                return ThermostatTab(self)
            case ModelName.EMULATOR:
                return EmulatorTab(self)

        raise ValueError(f"Unsupported model: {model!r}")

    def _prepare_window_before_show(self) -> None:
        """Prepare window layout and apply maximized state before showing it."""
        try:
            self.update_idletasks()
        except TclError as exc:
            Logger.write(
                LogLevel.WARNING,
                "Failed to flush idle layout tasks before showing main window. "
                f"({type(exc).__name__}: {exc})",
            )

        self._apply_best_initial_window_state()

        try:
            self.update_idletasks()
        except TclError as exc:
            Logger.write(
                LogLevel.WARNING,
                "Failed to flush idle layout tasks after window sizing. "
                f"({type(exc).__name__}: {exc})",
            )

    def _apply_best_initial_window_state(self) -> None:
        """Apply the best available maximized state for the current platform."""
        last_error: Exception | None = None

        for operation in self._get_maximize_operations():
            try:
                operation()
                if self._is_window_large_enough():
                    return
            except Exception as exc:
                last_error = exc

        try:
            self._apply_screen_geometry_fallback()
            if self._is_window_large_enough():
                return
        except Exception as exc:
            last_error = exc

        if last_error is not None:
            Logger.write(
                LogLevel.WARNING,
                "Failed to apply maximized window state. "
                f"({type(last_error).__name__}: {last_error})",
            )

    def _get_maximize_operations(self) -> tuple[callable, ...]:
        """Return platform-appropriate maximize operations in priority order."""
        if sys.platform.startswith("win"):
            return (
                lambda: self.state("zoomed"),
            )

        if sys.platform == "darwin":
            # Tk on macOS is less consistent with "zoomed".
            # Try the common options, then fall back to screen geometry.
            return (
                lambda: self.state("zoomed"),
                lambda: self.attributes("-zoomed", True),
            )

        # Linux / other Unix-like environments
        return (
            lambda: self.wm_attributes("-zoomed", True),
            lambda: self.attributes("-zoomed", True),
            lambda: self.state("zoomed"),
        )

    def _apply_screen_geometry_fallback(self) -> None:
        """Fallback to full-screen-sized geometry without entering true fullscreen."""
        screen_width = max(self.winfo_screenwidth(), 1)
        screen_height = max(self.winfo_screenheight(), 1)
        self.geometry(f"{screen_width}x{screen_height}+0+0")

    def _is_window_large_enough(self) -> bool:
        """Check whether the window is effectively maximized for practical purposes."""
        try:
            self.update_idletasks()

            screen_width = max(self.winfo_screenwidth(), 1)
            screen_height = max(self.winfo_screenheight(), 1)
            window_width = max(self.winfo_width(), 1)
            window_height = max(self.winfo_height(), 1)

            return (
                window_width >= int(screen_width * 0.9)
                and window_height >= int(screen_height * 0.9)
            )
        except Exception:
            return False

    def _show_window(self) -> None:
        """Show the fully prepared main window."""
        try:
            self.deiconify()
            self.lift()
        except TclError as exc:
            Logger.write(
                LogLevel.ALERT,
                "Failed to show main window. "
                f"({type(exc).__name__}: {exc})",
            )
            return

        try:
            self.focus_force()
        except TclError:
            pass

    def report_callback_exception(self, exc, val, tb) -> None:
        """Handle uncaught exceptions raised by Tk callbacks."""
        traceback_text = "".join(format_exception(exc, val, tb))
        message = (
            "Tk callback exception occurred. UI may become unstable.\n"
            f"{traceback_text}"
        )

        try:
            Logger.write(LogLevel.ALERT, message)
        except Exception:
            pass
