from __future__ import annotations

import tkinter as tk

import customtkinter as ctk

from logger import Logger, LogRecord


class LogBoxWidget(ctk.CTkFrame):
    """Show live logs in a scrollable text box."""

    def __init__(self, parent: ctk.CTkFrame, **kwargs) -> None:
        """Initialize the log box."""
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

        Logger.subscribe(self.print)

    def print(self, record: LogRecord) -> None:
        """Handle a new log record from Logger."""
        self.after(0, self._append_record, record)

    def _append_record(self, record: LogRecord) -> None:
        """Append one log line."""
        timestamp = record.timestamp.strftime("%H:%M:%S")
        line = f"[{timestamp}] [{record.level.name}] {record.message}\n"

        self.textbox.configure(state="normal")
        self.textbox.insert("end", line)
        self.textbox.configure(state="disabled")

        if self._autoscroll:
            self.textbox.see("end")

    def clear(self) -> None:
        """Clear visible log text."""
        self.textbox.configure(state="normal")
        self.textbox.delete("1.0", "end")
        self.textbox.configure(state="disabled")

    def reload(self) -> None:
        """Reload current widget content (same as clear)."""
        self.clear()

    def set_autoscroll(self, enabled: bool) -> None:
        """Enable or disable auto-scroll."""
        self._autoscroll = enabled

    def get_autoscroll(self) -> bool:
        """Return auto-scroll state."""
        return self._autoscroll

    def _bind_copy_shortcuts(self) -> None:
        """Bind copy shortcuts to text widgets."""
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
        """Show right-click copy menu."""
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
        """Copy selected text and stop default handler."""
        self._copy_selected_text()
        return "break"

    def _copy_selected_text(self) -> None:
        """Copy selected text to clipboard."""
        selected_text = self._get_selected_text()
        if not selected_text:
            return

        root = self.winfo_toplevel()
        root.clipboard_clear()
        root.clipboard_append(selected_text)
        # Ensure clipboard data stays after app exit.
        root.update()

    def _get_selected_text(self) -> str:
        """Get selected text from wrapper/internal widgets."""
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
        """Unsubscribe Logger before destroy."""
        Logger.unsubscribe(self.print)
        super().destroy()
