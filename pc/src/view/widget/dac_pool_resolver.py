from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from tkinter import filedialog
from tkinter import messagebox

import customtkinter as ctk

from logger import Logger, LogLevel
from storage import dac_pool_store


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


class DacPoolResolverWidget(ctk.CTkFrame):
    """Card-style widget for selecting and loading a DAC pool directory."""

    _DEFAULT_STATUS_TEXT = "Choose a valid DAC pool (folder of DAC certificate and key pairs)."
    _INVALID_STATUS_TEXT = "Not a valid DAC pool (folder required)."
    _VALID_STATUS_TEXT = "DAC pool loaded."
    _LOAD_ERROR_TEXT = (
        "Failed to load the DAC pool. "
        "Please select a valid folder containing DAC certificate and key pairs."
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
            text="DAC Pool",
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
        """Return current DAC pool directory path."""
        raw_path = dac_pool_store.pool_path
        if not raw_path:
            return None
        return Path(raw_path)

    @property
    def is_ready(self) -> bool:
        """Return whether a valid DAC pool is currently loaded."""
        return dac_pool_store.pool_path is not None

    def load_path(self, path: Path | None) -> None:
        """Load DAC pool directory and update widget state."""
        normalized_path = None
        if path is not None:
            normalized_path = str(path.expanduser().resolve())

        dac_pool_store.load(normalized_path)
        self._sync_from_store()
        self._publish_changed()

    def _on_browse(self) -> None:
        """Open folder chooser and attempt to load selected DAC pool."""
        initial_dir = self._path_entry.get().strip() or None

        selected_dir = filedialog.askdirectory(
            title="Select DAC Pool Folder",
            initialdir=initial_dir,
        )
        if not selected_dir:
            return

        selected_path = Path(selected_dir).expanduser().resolve()

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
        current_path = dac_pool_store.pool_path

        self._path_entry.delete(0, "end")

        if not current_path:
            self._set_default_status()
            return

        self._path_entry.insert(0, current_path)

        try:
            report = dac_pool_store.get_inventory_report()
        except Exception:
            self._set_invalid_status(self._INVALID_STATUS_TEXT)
            return

        self._set_valid_status(
            f"Total={report.total} / "
            f"Ready={report.ready} / "
            f"Progress={report.progress} / "
            f"Consumed={report.consumed} / "
            f"Error={report.error}"
        )

    def _set_default_status(self) -> None:
        """Show neutral status."""
        self._status_label.configure(
            text=self._DEFAULT_STATUS_TEXT,
            text_color=("gray45", "gray65"),
        )

    def _set_valid_status(self, message: str) -> None:
        """Show valid DAC pool summary."""
        self._status_label.configure(
            text=message,
            text_color="green",
        )

    def _set_invalid_status(self, message: str) -> None:
        """Show invalid DAC pool status."""
        self._status_label.configure(
            text=message,
            text_color="red",
        )

    def _show_error(self, message: str) -> None:
        """Show an error popup."""
        messagebox.showerror("DAC Pool Error", message)

    def _publish_changed(self) -> None:
        """Notify parent that widget state changed."""
        if self._on_changed is not None:
            self._on_changed()
