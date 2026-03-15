from __future__ import annotations

from enum import Enum
from typing import Any, Callable, NamedTuple, Optional

import customtkinter as ctk

from logger import Logger, LogLevel


class WorkerIndicatorState(str, Enum):
    IDLE = "IDLE"
    READY = "READY"
    PROGRESS = "PROGRESS"
    SUCCESS = "SUCCESS"
    FAIL = "FAIL"


class ProvisioningUserEvent(NamedTuple):
    name: str
    action: str


ProvisioningUserEventListener = Callable[[ProvisioningUserEvent], None]


_CARD_CORNER_RADIUS = 10
_CARD_BORDER_WIDTH = 1

_OUTER_TOP_PADY = (10, 0)

_CONTENT_PADX = 20
_TOP_PADY = 24
_SECTION_GAP_SMALL = 8
_SECTION_GAP = 14
_BOTTOM_PADY = 16

_INDICATOR_FONT_SIZE = 48
_MESSAGE_FONT_SIZE = 14
_BUTTON_FONT_SIZE = 24
_BUTTON_HEIGHT = 54
_NEXT_ACTION_FONT_SIZE = 15
_DISPATCHER_FONT_SIZE = 12


class ProvisionerWidget(ctk.CTkFrame):
    """Provisioning control and status widget."""

    _STATE_COLOR = {
        WorkerIndicatorState.IDLE: "#95A5A6",
        WorkerIndicatorState.READY: "#F5A623",
        WorkerIndicatorState.PROGRESS: "#3498DB",
        WorkerIndicatorState.SUCCESS: "#2ECC71",
        WorkerIndicatorState.FAIL: "#E74C3C",
    }

    def __init__(self, parent: ctk.CTkFrame, **kwargs) -> None:
        super().__init__(parent, fg_color="transparent", **kwargs)

        self._event_listener: Optional[ProvisioningUserEventListener] = None
        self._current_button_text = "START"

        self._build_ui()
        self.update_view("idle")

    def _build_ui(self) -> None:
        """Build widget layout."""
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self.container = ctk.CTkFrame(
            self,
            border_width=_CARD_BORDER_WIDTH,
            corner_radius=_CARD_CORNER_RADIUS,
        )
        self.container.grid(
            row=0,
            column=0,
            sticky="nsew",
            pady=_OUTER_TOP_PADY,
        )

        self.title_label = ctk.CTkLabel(
            self,
            text="  Provisioning  ",
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color=self.cget("fg_color"),
        )
        self.title_label.place(relx=0.5, y=10, anchor="center")
        self.title_label.lift()

        self.container.grid_columnconfigure(0, weight=1)
        self.container.grid_rowconfigure(0, weight=1)

        self._content = ctk.CTkFrame(self.container, fg_color="transparent")
        self._content.grid(
            row=0,
            column=0,
            sticky="nsew",
            padx=_CONTENT_PADX,
            pady=(18, _BOTTOM_PADY),
        )

        self._content.grid_columnconfigure(0, weight=1)
        self._content.grid_rowconfigure(0, weight=1)
        self._content.grid_rowconfigure(1, weight=0)
        self._content.grid_rowconfigure(2, weight=0)
        self._content.grid_rowconfigure(3, weight=0)
        self._content.grid_rowconfigure(4, weight=0)
        self._content.grid_rowconfigure(5, weight=1)

        self.worker_indicator = ctk.CTkLabel(
            self._content,
            text="",
            font=ctk.CTkFont(size=_INDICATOR_FONT_SIZE, weight="bold"),
            anchor="center",
            justify="center",
        )
        self.worker_indicator.grid(
            row=0,
            column=0,
            padx=0,
            pady=(_TOP_PADY, _SECTION_GAP_SMALL),
            sticky="ew",
        )

        self.status_message_label = ctk.CTkLabel(
            self._content,
            text="",
            font=ctk.CTkFont(size=_MESSAGE_FONT_SIZE),
            anchor="center",
            justify="center",
            wraplength=700,
        )
        self.status_message_label.grid(
            row=1,
            column=0,
            padx=0,
            pady=(0, _SECTION_GAP),
            sticky="ew",
        )

        self.primary_button = ctk.CTkButton(
            self._content,
            text="START",
            font=ctk.CTkFont(size=_BUTTON_FONT_SIZE, weight="bold"),
            height=_BUTTON_HEIGHT,
            command=self._on_primary_button_clicked,
        )
        self.primary_button.grid(
            row=2,
            column=0,
            padx=0,
            pady=(0, _SECTION_GAP),
            sticky="ew",
        )

        self.next_action_label = ctk.CTkLabel(
            self._content,
            text="",
            font=ctk.CTkFont(size=_NEXT_ACTION_FONT_SIZE, weight="bold"),
            anchor="w",
            justify="left",
            wraplength=760,
        )
        self.next_action_label.grid(
            row=3,
            column=0,
            padx=0,
            pady=(0, 6),
            sticky="ew",
        )

        self.dispatcher_status_label = ctk.CTkLabel(
            self._content,
            text="",
            font=ctk.CTkFont(size=_DISPATCHER_FONT_SIZE),
            anchor="w",
            justify="left",
            text_color=("gray45", "gray65"),
        )
        self.dispatcher_status_label.grid(
            row=4,
            column=0,
            padx=0,
            pady=(0, 0),
            sticky="ew",
        )

    def bind_manager_event_listener(self, manager: Any) -> None:
        """Subscribe to manager events and update UI on the main thread."""
        def _on_event(event: Any) -> None:
            event_name = getattr(event, "value", str(event))
            self.after(0, lambda: self.update_view(event_name))

        manager.subscribe_event(_on_event)

    def set_user_event_listener(
        self,
        listener: Optional[ProvisioningUserEventListener],
    ) -> None:
        """Register one listener for user-triggered actions."""
        self._event_listener = listener

    def update_view(self, event_name: str) -> None:
        """Update visible state from one manager event name."""
        states = {
            "idle": (
                WorkerIndicatorState.IDLE,
                "Provisioning is idle.",
                "Prepare the dispatcher connection.",
            ),
            "ready": (
                WorkerIndicatorState.READY,
                "Provisioning is ready.",
                "Press START to begin.",
            ),
            "progress": (
                WorkerIndicatorState.PROGRESS,
                "Provisioning in progress.",
                "Do not remove the device.",
            ),
            "success": (
                WorkerIndicatorState.SUCCESS,
                "Provisioning successful.",
                "Review results and press Finish.",
            ),
            "fail": (
                WorkerIndicatorState.FAIL,
                "Provisioning failed.",
                "Check device and press Finish.",
            ),
        }

        if event_name in states:
            state, message, instruction = states[event_name]
            self._apply_state(state, message, instruction)
            return

        if event_name == "enable_start":
            self._update_button("START", True)
            return

        if event_name == "disable_start":
            self._update_button("START", False)
            return

        if event_name == "enable_finish":
            self._update_button("Finish", True)
            return

        if event_name == "disable_finish":
            self._update_button("Finish", False)
            return

        if event_name == "dispatcher_ready":
            self._set_dispatcher_status(True)
            return

        if event_name == "dispatcher_not_ready":
            self._set_dispatcher_status(False)
            return

    def _apply_state(
        self,
        state: WorkerIndicatorState,
        message: str,
        instruction: str,
    ) -> None:
        """Apply one visual state."""
        self.worker_indicator.configure(
            text=state.value,
            text_color=self._STATE_COLOR.get(state, "white"),
        )
        self.status_message_label.configure(text=message)
        self.next_action_label.configure(text=f"Next: {instruction}")

    def _set_dispatcher_status(self, is_ready: bool) -> None:
        """Update dispatcher readiness text."""
        status = "Ready" if is_ready else "Not ready"
        self.dispatcher_status_label.configure(text=f"Dispatcher: {status}")

    def _update_button(self, text: str, enabled: bool) -> None:
        """Update primary button label and enabled state."""
        if text == "Finish" and not enabled and self._current_button_text.upper() != "FINISH":
            return

        self._current_button_text = text
        self.primary_button.configure(
            text=text,
            state="normal" if enabled else "disabled",
        )

    def _on_primary_button_clicked(self) -> None:
        """Emit one user action event."""
        action = "finish" if self._current_button_text.upper() == "FINISH" else "start"
        event_name = f"{action}_button_clicked"

        Logger.write(LogLevel.DEBUG, f"[USER_EVENT] Triggered {event_name}")

        if self._event_listener is None:
            return

        self._event_listener(
            ProvisioningUserEvent(
                name=event_name,
                action=action,
            )
        )
