from __future__ import annotations

import tkinter as tk

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
        self._copy_menu = tk.Menu(self, tearoff=0)
        self._copy_menu.add_command(label="Copy", command=self._copy_selected_text)
        self._bind_copy_shortcuts()

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

    def _bind_copy_shortcuts(self) -> None:
        """
        Bind copy shortcuts on both wrapper and internal text widget.
        """
        widgets = [self.textbox]
        internal_textbox = getattr(self.textbox, "_textbox", None)
        if internal_textbox is not None:
            widgets.append(internal_textbox)

        for widget in widgets:
            widget.bind("<Control-c>", self._on_copy, add="+")
            widget.bind("<Control-C>", self._on_copy, add="+")
            widget.bind("<Command-c>", self._on_copy, add="+")
            widget.bind("<Command-C>", self._on_copy, add="+")
            widget.bind("<Control-Insert>", self._on_copy, add="+")
            widget.bind("<Button-3>", self._show_copy_menu, add="+")
            widget.bind("<Button-2>", self._show_copy_menu, add="+")

    def _show_copy_menu(self, event) -> str:
        """
        Show right-click context menu with copy action.
        """
        selected_text = self._get_selected_text()
        self._copy_menu.entryconfigure(
            "Copy",
            state="normal" if selected_text else "disabled",
        )

        try:
            self._copy_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self._copy_menu.grab_release()

        return "break"

    def _on_copy(self, _event) -> str:
        """
        Copy the selected log text to clipboard when Ctrl+C is pressed.
        """
        self._copy_selected_text()
        return "break"

    def _copy_selected_text(self) -> None:
        """
        Copy current selection into clipboard.
        """
        selected_text = self._get_selected_text()
        if not selected_text:
            return

        root = self.winfo_toplevel()
        root.clipboard_clear()
        root.clipboard_append(selected_text)
        # Flush clipboard ownership to the OS so copied text survives app exit.
        root.update()

    def _get_selected_text(self) -> str:
        """
        Return selected text from wrapper/internal text widgets.
        """
        selected_text = ""

        for widget in (self.textbox, getattr(self.textbox, "_textbox", None)):
            if widget is None:
                continue

            try:
                selected_text = widget.selection_get()
            except Exception:
                try:
                    selected_text = widget.get("sel.first", "sel.last")
                except Exception:
                    continue

            if selected_text:
                break

        return selected_text

    def destroy(self) -> None:
        """
        Unsubscribe from the logger before destroying the view.
        """
        Logger.unsubscribe(self.print)
        super().destroy()
