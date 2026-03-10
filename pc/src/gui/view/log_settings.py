from __future__ import annotations

from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk

from logger import Logger, LogLevel, LogPresenterType, LogSaver

from .base import View
from .log_box import LogBoxView


class LogSettingsView(View):
    """
    Provide log-related controls such as clear, save, auto-clear-on-finish,
    and maximum visible log level.

    This view is intended to work together with LogBoxView.
    """

    def __init__(
        self,
        parent: ctk.CTkFrame,
        log_box_view: LogBoxView,
        **kwargs,
    ) -> None:
        """
        Initialize the log settings view.
        """
        super().__init__(parent, **kwargs)

        self._log_box_view = log_box_view
        self._auto_clear_on_finish_var = ctk.BooleanVar(value=False)
        self._level_var = ctk.StringVar(value=Logger.get_min_level().name)

        self.grid_columnconfigure(5, weight=1)

        self.clear_button = ctk.CTkButton(
            self,
            text="Clear",
            width=90,
            command=self._clear_logs,
        )
        self.clear_button.grid(row=0, column=0, padx=(8, 8), pady=8, sticky="w")

        self.save_button = ctk.CTkButton(
            self,
            text="Save",
            width=90,
            command=self._save_logs,
        )
        self.save_button.grid(row=0, column=1, padx=(0, 12), pady=8, sticky="w")

        self.auto_clear_checkbox = ctk.CTkCheckBox(
            self,
            text="Auto Clear on Finish",
            variable=self._auto_clear_on_finish_var,
        )
        self.auto_clear_checkbox.grid(row=0, column=2, padx=(0, 16), pady=8, sticky="w")

        self.level_label = ctk.CTkLabel(self, text="Max Level")
        self.level_label.grid(row=0, column=3, padx=(0, 8), pady=8, sticky="w")

        self.level_optionmenu = ctk.CTkOptionMenu(
            self,
            values=[level.name for level in LogLevel],
            variable=self._level_var,
            command=self._on_level_changed,
            width=120,
        )
        self.level_optionmenu.grid(row=0, column=4, padx=(0, 8), pady=8, sticky="w")
        self.level_optionmenu.set(Logger.get_min_level().name)

        self._event_handlers = {
            "clear": self._clear_logs,
            "save": self._save_logs,
            "finish": self.handle_finish,
            "enable_auto_clear_on_finish": lambda: self.set_auto_clear_on_finish(True),
            "disable_auto_clear_on_finish": lambda: self.set_auto_clear_on_finish(False),
            "set_max_level_debug": lambda: self.set_max_level(LogLevel.DEBUG),
            "set_max_level_progress": lambda: self.set_max_level(LogLevel.PROGRESS),
            "set_max_level_info": lambda: self.set_max_level(LogLevel.INFO),
            "set_max_level_warning": lambda: self.set_max_level(LogLevel.WARNING),
            "set_max_level_error": lambda: self.set_max_level(LogLevel.ERROR),
        }

    def _clear_logs(self) -> None:
        """
        Clear both logger state and visible log box content.
        """
        Logger.clear()
        self._log_box_view.clear()

    def _save_logs(self) -> None:
        """
        Save the currently visible logger records to a text file.

        The selected path is used as the base output path. The saver appends
        a timestamp suffix automatically.
        """
        path = filedialog.asksaveasfilename(
            title="Save Logs",
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
            initialfile="log_report.txt",
        )
        if not path:
            return

        try:
            output_path = LogSaver.save(
                records=Logger.get_records(),
                path=path,
                presenter_type=LogPresenterType.TEXT,
            )
        except Exception as exc:
            messagebox.showerror(
                "Save Logs",
                f"Failed to save logs.\n\n{exc}",
                parent=self,
            )
            return

        messagebox.showinfo(
            "Save Logs",
            f"Logs were saved successfully.\n\n{Path(output_path)}",
            parent=self,
        )

    def _on_level_changed(self, value: str) -> None:
        """
        Apply the selected logger level and refresh the visible log box.

        The current logger policy clears retained records when the level
        changes.
        """
        Logger.set_min_level(LogLevel[value])
        self._log_box_view.clear()

    def is_auto_clear_on_finish_enabled(self) -> bool:
        """
        Return whether auto-clear-on-finish is enabled.
        """
        return bool(self._auto_clear_on_finish_var.get())

    def set_auto_clear_on_finish(self, enabled: bool) -> None:
        """
        Update the auto-clear-on-finish option.
        """
        self._auto_clear_on_finish_var.set(enabled)

    def get_max_level(self) -> LogLevel:
        """
        Return the currently selected maximum visible log level.
        """
        return LogLevel[self._level_var.get()]

    def set_max_level(self, level: LogLevel) -> None:
        """
        Update the maximum visible log level selection and logger state.
        """
        self._level_var.set(level.name)
        Logger.set_min_level(level)
        self._log_box_view.clear()

    def handle_finish(self) -> None:
        """
        Apply post-finish behavior according to the current settings.
        """
        if self.is_auto_clear_on_finish_enabled():
            self._clear_logs()