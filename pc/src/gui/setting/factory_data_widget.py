from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional

import customtkinter as ctk
from tkinter import filedialog


class FactoryDataPoolWidget(ctk.CTkFrame):
    """
    UI widget for selecting the factory data pool directory.
    """

    def __init__(self, parent: ctk.CTkFrame, **kwargs):
        super().__init__(parent, fg_color="transparent", **kwargs)

        self._path_listener: Optional[Callable[[str], None]] = None

        self.grid_columnconfigure(0, weight=1)

        self._frame = ctk.CTkFrame(self, border_width=2, corner_radius=10)
        self._frame.grid(row=0, column=0, sticky="nsew", pady=(10, 0))
        self._frame.grid_columnconfigure(0, weight=1)

        self._title_label = ctk.CTkLabel(
            self,
            text="  Factory Data Pool  ",
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color=self.master.cget("fg_color"),
        )
        self._title_label.place(relx=0.5, y=10, anchor="center")
        self._title_label.lift()

        self._path_label = ctk.CTkLabel(
            self._frame,
            text="No folder selected",
            anchor="w",
            justify="left",
            wraplength=420,
        )
        self._path_label.grid(row=0, column=0, padx=20, pady=(24, 10), sticky="ew")

        self._select_button = ctk.CTkButton(
            self._frame,
            text="Select Folder",
            height=36,
            command=self._on_select_clicked,
        )
        self._select_button.grid(row=1, column=0, padx=20, pady=(0, 16), sticky="ew")

    def set_path_listener(self, listener: Optional[Callable[[str], None]]) -> None:
        """
        Register callback invoked when a new folder is selected.
        """
        self._path_listener = listener

    def set_path(self, path: str | Path) -> None:
        """
        Update the displayed path.
        """
        path_text = str(path)
        self._path_label.configure(text=path_text)

    def clear_path(self) -> None:
        """
        Reset the displayed path.
        """
        self._path_label.configure(text="No folder selected")

    def _on_select_clicked(self) -> None:
        """
        Open folder selection dialog.
        """
        selected = filedialog.askdirectory(title="Select Factory Data Pool Folder")

        if not selected:
            return

        self.set_path(selected)

        if self._path_listener is not None:
            try:
                self._path_listener(selected)
            except Exception:
                pass