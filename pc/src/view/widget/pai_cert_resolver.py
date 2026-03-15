from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from tkinter import filedialog
from tkinter import messagebox

import customtkinter as ctk

from logger import Logger, LogLevel
from storage import pai_cert_store


ChangedCallback = Callable[[], None]


_CARD_CORNER_RADIUS = 14
_CARD_BORDER_WIDTH = 1
_CARD_PADX = 20
_CARD_PADY_TOP = 18
_CARD_PADY_BOTTOM = 18

_LABEL_WIDTH = 130
_INPUT_HEIGHT = 35
_BROWSE_BUTTON_WIDTH = 110
_DESCRIPTION_WRAPLENGTH = 900


class PAICertResolverWidget(ctk.CTkFrame):
    """Card-style widget for selecting and loading the PAI certificate file."""

    _DEFAULT_STATUS_TEXT = "Choose a valid PAI certificate file (.pem)."
    _INVALID_STATUS_TEXT = "Not a valid PAI certificate file (.pem required)."
    _VALID_STATUS_TEXT = "Valid PAI certificate file loaded."
    _LOAD_ERROR_TEXT = (
        "Failed to load the PAI certificate file. "
        "Please select a valid .pem certificate file."
    )

    def __init__(
        self,
        parent: ctk.CTkFrame,
        on_changed: ChangedCallback | None = None,
        **kwargs,
    ) -> None:
        super().__init__(
            parent,
            corner_radius=_CARD_CORNER_RADIUS,
            border_width=_CARD_BORDER_WIDTH,
            **kwargs,
        )

        self._on_changed = on_changed

        self.grid_columnconfigure(1, weight=1)

        self._title_label = ctk.CTkLabel(
            self,
            text="PAI Certificate",
            anchor="nw",
            width=_LABEL_WIDTH,
            font=ctk.CTkFont(size=17, weight="bold"),
        )
        self._title_label.grid(
            row=0,
            column=0,
            sticky="nw",
            padx=(20, 12),
            pady=(_CARD_PADY_TOP, 8),
        )

        self._input_frame = ctk.CTkFrame(self, fg_color="transparent")
        self._input_frame.grid(
            row=0,
            column=1,
            sticky="ew",
            padx=(0, _CARD_PADX),
            pady=(_CARD_PADY_TOP, 8),
        )
        self._input_frame.grid_columnconfigure(0, weight=1)

        self._path_entry = ctk.CTkEntry(
            self._input_frame,
            height=_INPUT_HEIGHT,
            font=ctk.CTkFont(size=15),
        )
        self._path_entry.grid(
            row=0,
            column=0,
            sticky="ew",
            padx=(0, 10),
        )

        self._browse_button = ctk.CTkButton(
            self._input_frame,
            text="Browse",
            width=_BROWSE_BUTTON_WIDTH,
            height=_INPUT_HEIGHT,
            corner_radius=10,
            command=self._on_browse,
        )
        self._browse_button.grid(
            row=0,
            column=1,
            sticky="e",
        )

        self._status_label = ctk.CTkLabel(
            self,
            text=self._DEFAULT_STATUS_TEXT,
            anchor="e",
            justify="right",
            wraplength=_DESCRIPTION_WRAPLENGTH,
            font=ctk.CTkFont(size=13),
        )
        self._status_label.grid(
            row=1,
            column=0,
            columnspan=2,
            sticky="ew",
            padx=_CARD_PADX,
            pady=(0, _CARD_PADY_BOTTOM),
        )

        self._sync_from_store()

    @property
    def current_path(self) -> Path | None:
        """Return current PAI certificate file path."""
        raw_path = pai_cert_store.cert_path
        if not raw_path:
            return None
        return Path(raw_path)

    @property
    def is_ready(self) -> bool:
        """Return whether a valid PAI certificate is currently loaded."""
        return pai_cert_store.cert_path is not None

    def load_path(self, path: Path | None) -> None:
        """Load PAI certificate file and update widget state."""
        normalized_path = None
        if path is not None:
            normalized_path = str(path.expanduser().resolve())

        pai_cert_store.load(normalized_path)
        self._sync_from_store()
        self._publish_changed()

    def _on_browse(self) -> None:
        """Open file chooser and attempt to load selected PAI file."""
        current_path = self._path_entry.get().strip()

        filetypes = [
            (
                "Supported Files",
                " ".join(
                    f"*{extension}" for extension in pai_cert_store.expected_formats()
                ),
            ),
            ("All Files", "*.*"),
        ]

        selected_file = filedialog.askopenfilename(
            title="Select PAI Certificate File",
            initialdir=str(Path(current_path).parent) if current_path else None,
            filetypes=filetypes,
        )
        if not selected_file:
            return

        selected_path = Path(selected_file).expanduser().resolve()

        self._path_entry.delete(0, "end")
        self._path_entry.insert(0, str(selected_path))

        try:
            self.load_path(selected_path)
        except Exception as exc:
            Logger.write(LogLevel.ALERT, str(exc))
            self._set_invalid_status(self._INVALID_STATUS_TEXT)
            self._show_error(self._LOAD_ERROR_TEXT)

    def _sync_from_store(self) -> None:
        """Sync entry text and status label from store state."""
        current_path = pai_cert_store.cert_path

        self._path_entry.delete(0, "end")

        if not current_path:
            self._set_default_status()
            return

        self._path_entry.insert(0, current_path)
        self._set_valid_status(self._VALID_STATUS_TEXT)

    def _set_default_status(self) -> None:
        """Show neutral status."""
        self._status_label.configure(
            text=self._DEFAULT_STATUS_TEXT,
            text_color=("gray45", "gray65"),
        )

    def _set_valid_status(self, message: str) -> None:
        """Show valid PAI file status."""
        self._status_label.configure(
            text=message,
            text_color="green",
        )

    def _set_invalid_status(self, message: str) -> None:
        """Show invalid PAI file status."""
        self._status_label.configure(
            text=message,
            text_color="red",
        )

    def _show_error(self, message: str) -> None:
        """Show an error popup."""
        messagebox.showerror("PAI Certificate Error", message)

    def _publish_changed(self) -> None:
        """Notify parent that widget state changed."""
        if self._on_changed is not None:
            self._on_changed()
