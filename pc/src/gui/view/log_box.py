from __future__ import annotations

import customtkinter as ctk

from logger import Logger, LogRecord

from .base import View


class LogBoxView(View):
    """
    Display live log records in a scrollable text box.

    The view reflects the logger state and appends newly published records in
    real time.
    """

    def __init__(self, parent: ctk.CTkFrame, **kwargs) -> None:
        """
        Initialize the log box view.
        """
        super().__init__(parent, **kwargs)

        self._autoscroll = True

        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self.textbox = ctk.CTkTextbox(
            self,
            wrap="word",
            height=140,
        )
        self.textbox.grid(row=0, column=0, sticky="nsew", padx=(8, 0), pady=8)

        self.scrollbar = ctk.CTkScrollbar(self, command=self.textbox.yview)
        self.scrollbar.grid(row=0, column=1, sticky="ns", padx=(0, 8), pady=8)

        self.textbox.configure(yscrollcommand=self.scrollbar.set)
        self.textbox.configure(state="disabled")

        self._event_handlers = {
            "clear": self.clear,
            "reload": self.reload,
            "enable_autoscroll": lambda: self.set_autoscroll(True),
            "disable_autoscroll": lambda: self.set_autoscroll(False),
        }

        self._load_existing_records()
        Logger.subscribe(self.print)

    def _load_existing_records(self) -> None:
        """
        Load retained logger records into the text box.
        """
        for record in Logger.get_records():
            self._append_record(record)

    def print(self, record: LogRecord) -> None:
        """
        Receive a newly accepted log record from the logger.
        """
        self.after(0, self._append_record, record)

    def _append_record(self, record: LogRecord) -> None:
        """
        Append a log record to the text box.
        """
        timestamp = record.timestamp.strftime("%H:%M:%S")
        line = f"[{timestamp}] [{record.level.name}] {record.message}\n"

        self.textbox.configure(state="normal")
        self.textbox.insert("end", line)
        self.textbox.configure(state="disabled")

        if self._autoscroll:
            self.textbox.see("end")

    def clear(self) -> None:
        """
        Clear the visible text box content only.
        """
        self.textbox.configure(state="normal")
        self.textbox.delete("1.0", "end")
        self.textbox.configure(state="disabled")

    def reload(self) -> None:
        """
        Reload the visible content from the current logger state.
        """
        self.clear()
        self._load_existing_records()

    def set_autoscroll(self, enabled: bool) -> None:
        """
        Enable or disable automatic scrolling.
        """
        self._autoscroll = enabled

    def get_autoscroll(self) -> bool:
        """
        Return the current auto-scroll setting.
        """
        return self._autoscroll

    def destroy(self) -> None:
        """
        Unsubscribe from the logger before destroying the view.
        """
        Logger.unsubscribe(self.print)
        super().destroy()