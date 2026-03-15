from __future__ import annotations

from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk

from logger import Logger, LogLevel

from .log_box import LogBoxWidget


_BUTTON_WIDTH = 90
_LEVEL_MENU_WIDTH = 120

_CARD_CORNER_RADIUS = 10
_CARD_BORDER_WIDTH = 2

_OUTER_TOP_PADY = (10, 0)

_DESCRIPTION_PADX = 16
_DESCRIPTION_PADY = (20, 8)

_CHECKBOX_PADX = 16
_CHECKBOX_PADY = (0, 10)

_FORM_PADX = 16
_FORM_PADY = (0, 12)

_BUTTON_ROW_PADX = 16
_BUTTON_ROW_PADY = (0, 14)
_BUTTON_GAP = 8


class LogSettingWidget(ctk.CTkFrame):
    """Log controls card."""

    def __init__(
        self,
        parent: ctk.CTkFrame,
        log_box_widget: LogBoxWidget,
        **kwargs,
    ) -> None:
        super().__init__(parent, fg_color="transparent", **kwargs)

        self._log_box_widget = log_box_widget
        self._auto_clear_on_finish_var = ctk.BooleanVar(value=False)
        self._level_var = ctk.StringVar(value=Logger.get_min_level().name)

        self._build_ui()
        self._build_event_handlers()
        self._sync_level_from_logger()

    def _build_ui(self) -> None:
        """Build widget UI."""
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self._body = ctk.CTkFrame(
            self,
            border_width=_CARD_BORDER_WIDTH,
            corner_radius=_CARD_CORNER_RADIUS,
        )
        self._body.grid(
            row=0,
            column=0,
            sticky="nsew",
            pady=_OUTER_TOP_PADY,
        )

        self._title_label = ctk.CTkLabel(
            self,
            text="  Log Management  ",
            font=ctk.CTkFont(size=16, weight="bold"),
            fg_color=self.cget("fg_color"),
        )
        self._title_label.place(relx=0.5, y=10, anchor="center")
        self._title_label.lift()

        self._body.grid_columnconfigure(0, weight=1)
        self._body.grid_rowconfigure(0, weight=0)
        self._body.grid_rowconfigure(1, weight=0)
        self._body.grid_rowconfigure(2, weight=0)
        self._body.grid_rowconfigure(3, weight=0)

        self._description_label = ctk.CTkLabel(
            self._body,
            text="Manage visible logs and filtering options.",
            font=ctk.CTkFont(size=13),
            text_color=("gray45", "gray65"),
            anchor="w",
            justify="left",
            wraplength=300,
        )
        self._description_label.grid(
            row=0,
            column=0,
            padx=_DESCRIPTION_PADX,
            pady=_DESCRIPTION_PADY,
            sticky="ew",
        )

        self._auto_clear_checkbox = ctk.CTkCheckBox(
            self._body,
            text="Auto Clear on Finish",
            variable=self._auto_clear_on_finish_var,
        )
        self._auto_clear_checkbox.grid(
            row=1,
            column=0,
            padx=_CHECKBOX_PADX,
            pady=_CHECKBOX_PADY,
            sticky="w",
        )

        self._form_row = ctk.CTkFrame(self._body, fg_color="transparent")
        self._form_row.grid(
            row=2,
            column=0,
            padx=_FORM_PADX,
            pady=_FORM_PADY,
            sticky="ew",
        )
        self._form_row.grid_columnconfigure(0, weight=0)
        self._form_row.grid_columnconfigure(1, weight=1)

        self._level_label = ctk.CTkLabel(
            self._form_row,
            text="Min Level",
            anchor="w",
        )
        self._level_label.grid(
            row=0,
            column=0,
            padx=(0, 8),
            pady=0,
            sticky="w",
        )

        self._level_optionmenu = ctk.CTkOptionMenu(
            self._form_row,
            values=[level.name for level in LogLevel],
            variable=self._level_var,
            command=self._on_level_changed,
            width=_LEVEL_MENU_WIDTH,
        )
        self._level_optionmenu.grid(
            row=0,
            column=1,
            padx=0,
            pady=0,
            sticky="e",
        )

        self._button_row = ctk.CTkFrame(self._body, fg_color="transparent")
        self._button_row.grid(
            row=3,
            column=0,
            padx=_BUTTON_ROW_PADX,
            pady=_BUTTON_ROW_PADY,
            sticky="ew",
        )
        self._button_row.grid_columnconfigure(0, weight=0)
        self._button_row.grid_columnconfigure(1, weight=0)
        self._button_row.grid_columnconfigure(2, weight=1)

        self._clear_button = ctk.CTkButton(
            self._button_row,
            text="Clear",
            width=_BUTTON_WIDTH,
            command=self._clear_logs,
        )
        self._clear_button.grid(
            row=0,
            column=0,
            padx=(0, _BUTTON_GAP),
            pady=0,
            sticky="w",
        )

        self._save_button = ctk.CTkButton(
            self._button_row,
            text="Save",
            width=_BUTTON_WIDTH,
            command=self._save_logs,
        )
        self._save_button.grid(
            row=0,
            column=1,
            padx=0,
            pady=0,
            sticky="w",
        )

    def _build_event_handlers(self) -> None:
        """Build externally callable event handler map."""
        self._event_handlers = {
            "clear": self._clear_logs,
            "save": self._save_logs,
            "finish": self.handle_finish,
            "enable_auto_clear_on_finish": lambda: self.set_auto_clear_on_finish(True),
            "disable_auto_clear_on_finish": lambda: self.set_auto_clear_on_finish(
                False
            ),
            "set_max_level_debug": lambda: self.set_max_level(LogLevel.DEBUG),
            "set_max_level_progress": lambda: self.set_max_level(LogLevel.DEBUG),
            "set_max_level_info": lambda: self.set_max_level(LogLevel.WARNING),
            "set_max_level_warning": lambda: self.set_max_level(LogLevel.WARNING),
            "set_max_level_error": lambda: self.set_max_level(LogLevel.ERROR),
            "set_max_level_alert": lambda: self.set_max_level(LogLevel.ALERT),
        }

    def _sync_level_from_logger(self) -> None:
        """Sync option menu state from the current logger policy."""
        level_name = Logger.get_min_level().name
        self._level_var.set(level_name)
        self._level_optionmenu.set(level_name)

    @property
    def event_handlers(self) -> dict[str, callable]:
        """Return supported event handlers."""
        return self._event_handlers

    def _clear_logs(self) -> None:
        """Clear visible log text."""
        self._log_box_widget.clear()

    def _save_logs(self) -> None:
        """Save currently visible log text to a file."""
        path = filedialog.asksaveasfilename(
            title="Save Logs",
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
            initialfile="log_report.txt",
        )
        if not path:
            return

        text = self._visible_log_text()
        if not text:
            messagebox.showinfo(
                "Save Logs",
                "There is no visible log text to save.",
                parent=self,
            )
            return

        try:
            Path(path).write_text(text, encoding="utf-8")
        except Exception as exc:
            messagebox.showerror(
                "Save Logs",
                f"Failed to save logs.\n\n{exc}",
                parent=self,
            )
            return

        messagebox.showinfo(
            "Save Logs",
            f"Logs were saved successfully.\n\n{path}",
            parent=self,
        )

    def _visible_log_text(self) -> str:
        """Return currently visible log text."""
        return self._log_box_widget.textbox.get("1.0", "end-1c")

    def _on_level_changed(self, value: str) -> None:
        """Apply the selected logger minimum level."""
        self.set_max_level(LogLevel[value])

    def is_auto_clear_on_finish_enabled(self) -> bool:
        """Return whether auto-clear-on-finish is enabled."""
        return bool(self._auto_clear_on_finish_var.get())

    def set_auto_clear_on_finish(self, enabled: bool) -> None:
        """Set auto-clear-on-finish state."""
        self._auto_clear_on_finish_var.set(enabled)

    def get_max_level(self) -> LogLevel:
        """Return the selected visible level."""
        return LogLevel[self._level_var.get()]

    def set_max_level(self, level: LogLevel) -> None:
        """Set logger minimum level and refresh visible logs."""
        self._level_var.set(level.name)
        self._level_optionmenu.set(level.name)
        Logger.set_min_level(level)
        self._log_box_widget.clear()

    def handle_finish(self) -> None:
        """Apply post-finish behavior."""
        if self.is_auto_clear_on_finish_enabled():
            self._clear_logs()

    def set_controls_enabled(self, enabled: bool) -> None:
        """Enable or disable all interactive controls."""
        state = "normal" if enabled else "disabled"

        self._clear_button.configure(state=state)
        self._save_button.configure(state=state)
        self._auto_clear_checkbox.configure(state=state)
        self._level_optionmenu.configure(state=state)

    def invoke_event(self, name: str) -> bool:
        """Invoke one registered event by name. Returns True if handled."""
        handler = self._event_handlers.get(name)
        if handler is None:
            return False

        handler()
        return True
