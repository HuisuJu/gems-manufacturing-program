from __future__ import annotations

from enum import Enum

from typing import Callable, NamedTuple, Optional

import customtkinter as ctk

from logger import Logger, LogLevel


class WorkerIndicatorState(str, Enum):
    """
    Visual provisioning states shown by the view.
    """

    IDLE = "IDLE"
    READY = "READY"
    PROGRESS = "PROGRESS"
    SUCCESS = "SUCCESS"
    FAIL = "FAIL"


class ProvisioningUserEvent(NamedTuple):
    """
    User action emitted by the provisioning view.
    """

    name: str
    action: str


ProvisioningUserEventListener = Callable[[ProvisioningUserEvent], None]


class ProvisioningView(ctk.CTkFrame):
    """
    Provisioning view widget.

    This view exposes named trigger events so that background model/service
    code can request UI updates without directly manipulating widgets.
    """

    _STATE_COLOR: dict[WorkerIndicatorState, str] = {
        WorkerIndicatorState.IDLE: "#95A5A6",
        WorkerIndicatorState.READY: "#F5A623",
        WorkerIndicatorState.PROGRESS: "#3498DB",
        WorkerIndicatorState.SUCCESS: "#2ECC71",
        WorkerIndicatorState.FAIL: "#E74C3C",
    }

    def __init__(self, parent: ctk.CTkFrame, **kwargs) -> None:
        """
        Initialize the provisioning view.
        """
        super().__init__(parent, **kwargs)

        self._event_listener: ProvisioningUserEventListener | None = None
        self._state = WorkerIndicatorState.IDLE
        self._current_button_text = "START"

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=0)
        self.grid_rowconfigure(1, weight=0)
        self.grid_rowconfigure(2, weight=1)

        self.frame = ctk.CTkFrame(self, border_width=2, corner_radius=10)
        self.frame.grid(row=0, column=0, sticky="nsew", pady=(10, 0))
        self.frame.grid_columnconfigure(0, weight=1)

        self.title_label = ctk.CTkLabel(
            self,
            text="  Provisioning  ",
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color=self.master.cget("fg_color"),
        )
        self.title_label.place(relx=0.5, y=10, anchor="center")
        self.title_label.lift()

        self.worker_indicator = ctk.CTkLabel(
            self.frame,
            text="",
            font=ctk.CTkFont(size=48, weight="bold"),
            anchor="center",
        )
        self.worker_indicator.grid(
            row=0,
            column=0,
            padx=20,
            pady=(24, 8),
            sticky="ew",
        )

        self.status_message_label = ctk.CTkLabel(
            self.frame,
            text="",
            font=ctk.CTkFont(size=14),
            anchor="center",
            justify="center",
            wraplength=420,
        )
        self.status_message_label.grid(
            row=1,
            column=0,
            padx=20,
            pady=(0, 14),
            sticky="ew",
        )

        self.primary_button = ctk.CTkButton(
            self.frame,
            text="START",
            font=ctk.CTkFont(size=24, weight="bold"),
            height=54,
            command=self._on_primary_button_clicked,
        )
        self.primary_button.grid(row=2, column=0, padx=20, pady=(0, 12), sticky="ew")

        self.next_action_label = ctk.CTkLabel(
            self.frame,
            text="",
            font=ctk.CTkFont(size=15, weight="bold"),
            anchor="w",
            justify="left",
            wraplength=420,
        )
        self.next_action_label.grid(
            row=3,
            column=0,
            padx=20,
            pady=(0, 10),
            sticky="ew",
        )

        self.dispatcher_status_label = ctk.CTkLabel(
            self.frame,
            text="",
            font=ctk.CTkFont(size=12),
            anchor="w",
            justify="left",
        )
        self.dispatcher_status_label.grid(
            row=4,
            column=0,
            padx=20,
            pady=(0, 16),
            sticky="ew",
        )

        self._event_handlers = {
            "idle": self._handle_idle,
            "ready": self._handle_ready,
            "progress": self._handle_progress,
            "success": self._handle_success,
            "fail": self._handle_fail,
            "dispatcher_ready": self._handle_dispatcher_ready,
            "dispatcher_not_ready": self._handle_dispatcher_not_ready,
            "enable_start": self._handle_enable_start,
            "disable_start": self._handle_disable_start,
            "enable_finish": self._handle_enable_finish,
            "disable_finish": self._handle_disable_finish,
        }

        self._handle_idle()
        self._handle_dispatcher_not_ready()
        self._handle_disable_start()
        self._handle_disable_finish()

    def set_user_event_listener(
        self,
        listener: Optional[ProvisioningUserEventListener],
    ) -> None:
        """
        Set the user event listener.
        """
        self._event_listener = listener

    def set_worker_indicator_state(self, state: WorkerIndicatorState) -> None:
        """
        Update the worker indicator state.
        """
        self._state = state
        self.worker_indicator.configure(
            text=state.value,
            text_color=self._STATE_COLOR.get(state, "white"),
        )

    def set_status_message(self, text: str) -> None:
        """
        Update the main status message.
        """
        self.status_message_label.configure(text=text)

    def set_next_instruction(self, text: str) -> None:
        """
        Update the next-action instruction text.
        """
        self.next_action_label.configure(text=f"Next: {text}")

    def set_dispatcher_status(self, is_ready: bool) -> None:
        """
        Update the dispatcher readiness display.
        """
        status_text = "Dispatcher: Ready" if is_ready else "Dispatcher: Not ready"
        self.dispatcher_status_label.configure(text=status_text)

    def set_primary_button(self, text: str, enabled: bool) -> None:
        """
        Update the primary button state.
        """
        self._current_button_text = text
        self.primary_button.configure(
            text=text,
            state="normal" if enabled else "disabled",
        )

    def handle_user_event(self, name: str, action: str) -> None:
        """
        Emit one user event from the view.
        """
        event = ProvisioningUserEvent(name=name, action=action)
        Logger.write(LogLevel.PROGRESS, f"[USER_EVENT] {event.name}: {event.action}")

        if self._event_listener is None:
            return

        try:
            self._event_listener(event)
        except Exception as exc:
            Logger.write(
                LogLevel.WARNING,
                f"[USER_EVENT] listener error ({type(exc).__name__}: {exc})",
            )

    def _on_primary_button_clicked(self) -> None:
        """
        Handle primary button clicks.
        """
        button_text_upper = self._current_button_text.strip().upper()

        if button_text_upper == "FINISH":
            self.handle_user_event(
                name="finish_button_clicked",
                action="finish",
            )
            return

        self.handle_user_event(
            name="start_button_clicked",
            action="start",
        )

    def _handle_idle(self) -> None:
        """
        Render the idle state.
        """
        self.set_worker_indicator_state(WorkerIndicatorState.IDLE)
        self.set_status_message("Provisioning is idle.")
        self.set_next_instruction("Prepare the dispatcher/device connection first.")

    def _handle_ready(self) -> None:
        """
        Render the ready state.
        """
        self.set_worker_indicator_state(WorkerIndicatorState.READY)
        self.set_status_message("Provisioning is ready.")
        self.set_next_instruction("Press START to begin provisioning.")

    def _handle_progress(self) -> None:
        """
        Render the progress state.
        """
        self.set_worker_indicator_state(WorkerIndicatorState.PROGRESS)
        self.set_status_message("Provisioning is in progress.")
        self.set_next_instruction(
            "Wait until provisioning completes. Do not remove the device."
        )

    def _handle_success(self) -> None:
        """
        Render the success state.
        """
        self.set_worker_indicator_state(WorkerIndicatorState.SUCCESS)
        self.set_status_message("Provisioning completed successfully.")
        self.set_next_instruction(
            "Review the result, perform any follow-up action, then press Finish."
        )

    def _handle_fail(self) -> None:
        """
        Render the failure state.
        """
        self.set_worker_indicator_state(WorkerIndicatorState.FAIL)
        self.set_status_message("Provisioning failed.")
        self.set_next_instruction(
            "Review the failure reason, check the device, then press Finish."
        )

    def _handle_dispatcher_ready(self) -> None:
        """
        Render dispatcher-ready status.
        """
        self.set_dispatcher_status(True)

    def _handle_dispatcher_not_ready(self) -> None:
        """
        Render dispatcher-not-ready status.
        """
        self.set_dispatcher_status(False)

    def _handle_enable_start(self) -> None:
        """
        Enable the START action.
        """
        self.set_primary_button(text="START", enabled=True)

    def _handle_disable_start(self) -> None:
        """
        Disable the START action.
        """
        self.set_primary_button(text="START", enabled=False)

    def _handle_enable_finish(self) -> None:
        """
        Enable the Finish action.
        """
        self.set_primary_button(text="Finish", enabled=True)

    def _handle_disable_finish(self) -> None:
        """
        Disable the Finish action.
        """
        if self._current_button_text.strip().upper() != "FINISH":
            return
        self.set_primary_button(text="Finish", enabled=False)

    def trigger(self, event_name: str) -> None:
        """Dispatch one named event."""
        handler = self._event_handlers.get(event_name)
        if handler is not None:
            handler()
