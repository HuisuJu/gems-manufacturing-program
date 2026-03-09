from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Callable, Optional

import customtkinter as ctk

from logger import Logger, LogLevel
from provision import ProvisionManagerEvent, ProvisionUIState


class WorkerIndicatorState(str, Enum):
    IDLE = "IDLE"
    READY = "READY"
    PROGRESS = "PROGRESS"
    SUCCESS = "SUCCESS"
    FAIL = "FAIL"


@dataclass(slots=True)
class ProvisioningUserEvent:
    name: str
    message: str


class ProvisioningControlWidget(ctk.CTkFrame):
    _STATE_COLOR: dict[WorkerIndicatorState, str] = {
        WorkerIndicatorState.IDLE: "#95A5A6",
        WorkerIndicatorState.READY: "#F5A623",
        WorkerIndicatorState.PROGRESS: "#3498DB",
        WorkerIndicatorState.SUCCESS: "#2ECC71",
        WorkerIndicatorState.FAIL: "#E74C3C",
    }

    def __init__(self, parent: ctk.CTkFrame, **kwargs):
        super().__init__(parent, fg_color="transparent", **kwargs)

        self._event_listener: Optional[Callable[[ProvisioningUserEvent], None]] = None
        self._state = WorkerIndicatorState.IDLE
        self._current_button_text = "START"
        self._current_manager_event: Optional[ProvisionManagerEvent] = None

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
        self.worker_indicator.grid(row=0, column=0, padx=20, pady=(24, 8), sticky="ew")

        self.status_message_label = ctk.CTkLabel(
            self.frame,
            text="",
            font=ctk.CTkFont(size=14),
            anchor="center",
            justify="center",
            wraplength=420,
        )
        self.status_message_label.grid(row=1, column=0, padx=20, pady=(0, 14), sticky="ew")

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
        self.next_action_label.grid(row=3, column=0, padx=20, pady=(0, 10), sticky="ew")

        self.dispatcher_status_label = ctk.CTkLabel(
            self.frame,
            text="",
            font=ctk.CTkFont(size=12),
            anchor="w",
            justify="left",
        )
        self.dispatcher_status_label.grid(row=4, column=0, padx=20, pady=(0, 16), sticky="ew")

        self.set_worker_indicator_state(WorkerIndicatorState.IDLE)
        self.set_status_message("Provision manager is not ready yet.")
        self.set_next_instruction("Connect the device path and wait until provisioning becomes ready.")
        self.set_dispatcher_status(False)
        self.set_primary_button(text="START", enabled=False)

    def apply_manager_event(self, event: ProvisionManagerEvent) -> None:
        """
        Apply a ProvisionManagerEvent to the widget.

        This is the main integration point between the GUI and ProvisionManager.
        """
        self._current_manager_event = event

        self.set_dispatcher_status(event.dispatcher_ready)
        self.set_status_message(event.message)
        self.set_primary_button(
            text=event.button_text,
            enabled=event.start_enabled or event.finish_enabled,
        )

        if event.ui_state == ProvisionUIState.READY:
            self.set_worker_indicator_state(WorkerIndicatorState.READY)
            self.set_next_instruction("Press START to begin provisioning.")
            return

        if event.ui_state == ProvisionUIState.PROGRESS:
            self.set_worker_indicator_state(WorkerIndicatorState.PROGRESS)
            self.set_next_instruction("Wait until provisioning completes. Do not remove the device.")
            return

        if event.ui_state == ProvisionUIState.SUCCESS:
            self.set_worker_indicator_state(WorkerIndicatorState.SUCCESS)
            self.set_next_instruction("Review the result, perform any follow-up action, then press Finish.")
            return

        if event.ui_state == ProvisionUIState.FAIL:
            self.set_worker_indicator_state(WorkerIndicatorState.FAIL)
            self.set_next_instruction("Review the failure reason, check the device, then press Finish.")
            return

        self.set_worker_indicator_state(WorkerIndicatorState.IDLE)
        if event.dispatcher_ready:
            self.set_next_instruction("Provisioning is idle. Press START when ready.")
        else:
            self.set_next_instruction("Prepare the dispatcher/device connection first.")

    def set_worker_indicator_state(self, state: WorkerIndicatorState) -> None:
        """
        Update the large provisioning state indicator.
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
        Update the next operator instruction text.
        """
        self.next_action_label.configure(text=f"Next: {text}")

    def set_dispatcher_status(self, is_ready: bool) -> None:
        """
        Update the dispatcher readiness label.
        """
        status_text = "Dispatcher: Ready" if is_ready else "Dispatcher: Not ready"
        self.dispatcher_status_label.configure(text=status_text)

    def set_primary_button(self, text: str, enabled: bool) -> None:
        """
        Update the primary action button text and enabled state.
        """
        self._current_button_text = text
        self.primary_button.configure(
            text=text,
            state="normal" if enabled else "disabled",
        )

    def set_start_enabled(self, enabled: bool) -> None:
        """
        Backward-compatible helper for older callers.

        This method now simply enables or disables the primary button without
        changing its current label.
        """
        self.primary_button.configure(state="normal" if enabled else "disabled")

    def set_user_event_listener(
        self,
        listener: Optional[Callable[[ProvisioningUserEvent], None]],
    ) -> None:
        """
        Register a user event listener.
        """
        self._event_listener = listener

    def handle_user_event(self, name: str, message: str) -> None:
        """
        Emit a user event to the external listener.
        """
        event = ProvisioningUserEvent(name=name, message=message)
        Logger.write(LogLevel.PROGRESS, f"[USER_EVENT] {event.name}: {event.message}")
        if self._event_listener is not None:
            try:
                self._event_listener(event)
            except Exception as e:
                Logger.write(
                    LogLevel.WARNING,
                    f"[USER_EVENT] listener error ({type(e).__name__}: {e})",
                )

    def _on_primary_button_clicked(self) -> None:
        """
        Handle the primary action button.

        The current button role is determined by the latest manager event.
        """
        button_text_upper = self._current_button_text.strip().upper()

        if button_text_upper == "FINISH":
            self.handle_user_event(
                name="finish_button_clicked",
                message="Operator pressed Finish.",
            )
            return

        self.handle_user_event(
            name="start_button_clicked",
            message="Operator pressed START.",
        )