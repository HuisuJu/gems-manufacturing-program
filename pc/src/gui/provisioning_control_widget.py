from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Callable, Optional

import customtkinter as ctk

from logger import Logger, LogLevel


class WorkerIndicatorState(str, Enum):
    IDLE = "IDLE"
    SUCCESS = "SUCCESS"
    FAIL = "FAIL"
    DISCONNECTED = "DISCONNECTED"


@dataclass(slots=True)
class ProvisioningUserEvent:
    name: str
    message: str


class ProvisioningControlWidget(ctk.CTkFrame):
    _STATE_COLOR: dict[WorkerIndicatorState, str] = {
        WorkerIndicatorState.IDLE: "#F5A623",
        WorkerIndicatorState.SUCCESS: "#2ECC71",
        WorkerIndicatorState.FAIL: "#E74C3C",
        WorkerIndicatorState.DISCONNECTED: "#95A5A6",
    }

    def __init__(self, parent: ctk.CTkFrame, **kwargs):
        super().__init__(parent, fg_color="transparent", **kwargs)

        self._event_listener: Optional[Callable[[ProvisioningUserEvent], None]] = None
        self._state = WorkerIndicatorState.DISCONNECTED

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=0)
        self.grid_rowconfigure(1, weight=0)
        self.grid_rowconfigure(2, weight=1)

        self.frame = ctk.CTkFrame(self, border_width=2, corner_radius=10)
        self.frame.grid(row=0, column=0, sticky="nsew", pady=(10, 0))
        self.frame.grid_columnconfigure(0, weight=1)
        self.frame.grid_rowconfigure(1, weight=1)

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
        self.worker_indicator.grid(row=1, column=0, padx=20, pady=(20, 14), sticky="ew")

        self.start_button = ctk.CTkButton(
            self.frame,
            text="START",
            font=ctk.CTkFont(size=24, weight="bold"),
            height=54,
            command=self._on_start,
        )
        self.start_button.grid(row=2, column=0, padx=20, pady=(0, 12), sticky="ew")

        self.next_action_label = ctk.CTkLabel(
            self.frame,
            text="",
            font=ctk.CTkFont(size=15, weight="bold"),
            anchor="w",
            justify="left",
        )
        self.next_action_label.grid(row=3, column=0, padx=20, pady=(0, 16), sticky="ew")

        self.set_next_instruction("Connect serial port and press START to begin provisioning.")
        self.set_worker_indicator_state(WorkerIndicatorState.DISCONNECTED)

    def set_worker_indicator_state(self, state: WorkerIndicatorState) -> None:
        self._state = state
        self.worker_indicator.configure(
            text=state.value,
            text_color=self._STATE_COLOR.get(state, "white"),
        )

    def set_next_instruction(self, text: str) -> None:
        self.next_action_label.configure(text=f"Next: {text}")

    def set_start_enabled(self, enabled: bool) -> None:
        self.start_button.configure(state="normal" if enabled else "disabled")

    def set_user_event_listener(
        self,
        listener: Optional[Callable[[ProvisioningUserEvent], None]],
    ) -> None:
        self._event_listener = listener

    def handle_user_event(self, name: str, message: str) -> None:
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

    def _on_start(self) -> None:
        self.handle_user_event(
            name="start_button_clicked",
            message="Operator pressed START. No provisioning action is executed yet.",
        )
