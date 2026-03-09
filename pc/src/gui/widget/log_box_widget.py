from __future__ import annotations

import customtkinter as ctk

from logger import Logger, LogRecord


class LogBoxWidget(ctk.CTkFrame):
    """
    Displays live log records in a scrollable text box.

    The widget reflects the logger state and appends newly published
    records in real time.
    """

    def __init__(self, parent: ctk.CTkFrame, **kwargs):
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

        self._load_existing_records()
        Logger.subscribe(self.print)

    def _load_existing_records(self) -> None:
        """
        Loads retained logger records into the text box.
        """
        for record in Logger.get_records():
            self._append_record(record)

    def print(self, record: LogRecord) -> None:
        """
        Receives a newly accepted log record from the logger.
        """
        self.after(0, self._append_record, record)

    def _append_record(self, record: LogRecord) -> None:
        """
        Appends a log record to the text box.
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
        Clears the visible text box content only.
        """
        self.textbox.configure(state="normal")
        self.textbox.delete("1.0", "end")
        self.textbox.configure(state="disabled")

    def reload(self) -> None:
        """
        Reloads the visible content from the current logger state.
        """
        self.clear()
        self._load_existing_records()

    def set_autoscroll(self, enabled: bool) -> None:
        """
        Enables or disables automatic scrolling.
        """
        self._autoscroll = enabled

    def get_autoscroll(self) -> bool:
        """
        Returns the current auto-scroll setting.
        """
        return self._autoscroll

    def destroy(self) -> None:
        """
        Unsubscribes from the logger before destroying the widget.
        """
        Logger.unsubscribe(self.print)
        super().destroy()