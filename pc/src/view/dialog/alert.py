from __future__ import annotations

import tkinter as tk

import customtkinter as ctk


class AlertDialog(ctk.CTkToplevel):
    """Top-level alert dialog with a close button."""

    def __init__(self, master: tk.Misc, title: str, message: str) -> None:
        super().__init__(master)

        self.title(title)
        self.resizable(False, False)

        self.grid_columnconfigure(0, weight=1)

        self._message_label = ctk.CTkLabel(
            self,
            text=message,
            justify="left",
            anchor="w",
            wraplength=420,
        )
        self._message_label.grid(
            row=0,
            column=0,
            padx=16,
            pady=(16, 10),
            sticky="ew",
        )

        self._close_button = ctk.CTkButton(
            self,
            text="Close",
            width=96,
            command=self._on_close,
        )
        self._close_button.grid(
            row=1,
            column=0,
            padx=16,
            pady=(0, 16),
            sticky="e",
        )

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self._show_centered()

    def _on_close(self) -> None:
        """Close the dialog safely."""
        try:
            self.grab_release()
        except tk.TclError:
            pass
        self.destroy()

    def _show_centered(self) -> None:
        """Show the dialog in front and centered on screen."""
        self.update_idletasks()
        width = self.winfo_reqwidth()
        height = self.winfo_reqheight()
        x = (self.winfo_screenwidth() - width) // 2
        y = (self.winfo_screenheight() - height) // 2

        self.geometry(f"{width}x{height}+{x}+{y}")

        try:
            self.deiconify()
            self.lift()
            self.grab_set()
            self.focus_force()
        except tk.TclError:
            pass
