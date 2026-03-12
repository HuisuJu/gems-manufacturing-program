from __future__ import annotations

from pathlib import Path
from tkinter import filedialog
from tkinter import messagebox

import customtkinter as ctk


class AttestationPathResolverError(Exception):
    """
    Base exception for attestation path resolver failures.
    """


class AttestationPathResolverConfigurationError(AttestationPathResolverError):
    """
    Raised when required configuration is missing or invalid.
    """


class PAICertResolverFrame(ctk.CTkFrame):
    """
    GUI frame for selecting and validating a PAI certificate file.

    This widget does not use global settings.
    It owns the currently loaded file path internally.

    Features:
        - Select PAI certificate file from file dialog
        - Load PAI certificate file
        - Show current file path
        - Refresh current file
        - Clear current selection
        - Show status/error message
    """

    def __init__(self, master, **kwargs) -> None:
        super().__init__(master, **kwargs)

        self._path: Path | None = None

        self.grid_columnconfigure(1, weight=1)

        self._title_label = ctk.CTkLabel(
            self,
            text="PAI Certificate File",
            anchor="w",
            font=ctk.CTkFont(size=16, weight="bold"),
        )
        self._title_label.grid(
            row=0,
            column=0,
            columnspan=3,
            sticky="ew",
            padx=12,
            pady=(12, 6),
        )

        self._path_label = ctk.CTkLabel(
            self,
            text="File",
            anchor="w",
        )
        self._path_label.grid(
            row=1,
            column=0,
            sticky="w",
            padx=(12, 6),
            pady=6,
        )

        self._path_entry = ctk.CTkEntry(self)
        self._path_entry.grid(
            row=1,
            column=1,
            sticky="ew",
            padx=6,
            pady=6,
        )

        self._browse_button = ctk.CTkButton(
            self,
            text="Browse",
            width=100,
            command=self._on_browse,
        )
        self._browse_button.grid(
            row=1,
            column=2,
            sticky="e",
            padx=(6, 12),
            pady=6,
        )

        self._button_row = ctk.CTkFrame(self, fg_color="transparent")
        self._button_row.grid(
            row=2,
            column=0,
            columnspan=3,
            sticky="ew",
            padx=12,
            pady=(0, 8),
        )
        self._button_row.grid_columnconfigure((0, 1, 2), weight=1)

        self._load_button = ctk.CTkButton(
            self._button_row,
            text="Load",
            command=self._on_load,
        )
        self._load_button.grid(
            row=0,
            column=0,
            sticky="ew",
            padx=(0, 4),
            pady=0,
        )

        self._refresh_button = ctk.CTkButton(
            self._button_row,
            text="Refresh",
            command=self._on_refresh,
        )
        self._refresh_button.grid(
            row=0,
            column=1,
            sticky="ew",
            padx=4,
            pady=0,
        )

        self._clear_button = ctk.CTkButton(
            self._button_row,
            text="Clear",
            command=self._on_clear,
        )
        self._clear_button.grid(
            row=0,
            column=2,
            sticky="ew",
            padx=(4, 0),
            pady=0,
        )

        self._status_label = ctk.CTkLabel(
            self,
            text="No PAI certificate file loaded.",
            anchor="w",
            justify="left",
            wraplength=700,
        )
        self._status_label.grid(
            row=3,
            column=0,
            columnspan=3,
            sticky="ew",
            padx=12,
            pady=(6, 12),
        )

    @property
    def path(self) -> Path | None:
        """
        Return the currently loaded PAI certificate file path.
        """
        return self._path

    def get_path(self) -> Path:
        """
        Return the configured PAI certificate file path.

        Raises:
            AttestationPathResolverConfigurationError:
                If the PAI certificate file has not been loaded.
        """
        if self._path is None:
            raise AttestationPathResolverConfigurationError(
                "The PAI certificate file has not been configured."
            )

        return self._path

    def load_path(self, path: Path | None) -> None:
        """
        Load a PAI certificate file path into the widget.

        Args:
            path: PAI certificate file path, or None to clear current selection.
        """
        if path is None:
            self._path = None
            self._path_entry.delete(0, "end")
            self._set_status("No PAI certificate file loaded.")
            return

        resolved = path.expanduser().resolve()

        if not resolved.exists():
            raise AttestationPathResolverConfigurationError(
                f"The PAI certificate file does not exist: '{resolved}'."
            )

        if not resolved.is_file():
            raise AttestationPathResolverConfigurationError(
                f"The PAI certificate path is not a file: '{resolved}'."
            )

        self._path = resolved
        self._path_entry.delete(0, "end")
        self._path_entry.insert(0, str(resolved))
        self._set_status(f"PAI certificate file loaded successfully: {resolved}")

    def _on_browse(self) -> None:
        """
        Open file selection dialog and put the selected path into the entry.
        """
        selected = filedialog.askopenfilename(
            title="Select PAI Certificate File",
            filetypes=[
                ("Certificate Files", "*.der *.pem *.crt *.cer"),
                ("All Files", "*.*"),
            ],
        )
        if not selected:
            return

        self._path_entry.delete(0, "end")
        self._path_entry.insert(0, selected)

    def _on_load(self) -> None:
        """
        Load the file currently written in the path entry.
        """
        raw_path = self._path_entry.get().strip()
        if not raw_path:
            self._show_error("Please select a PAI certificate file first.")
            return

        try:
            self.load_path(Path(raw_path))
        except AttestationPathResolverError as exc:
            self._set_status(str(exc))
            self._show_error(str(exc))

    def _on_refresh(self) -> None:
        """
        Reload the currently loaded PAI certificate file.
        """
        if self._path is None:
            self._show_error("There is no PAI certificate file to refresh.")
            return

        try:
            self.load_path(self._path)
        except AttestationPathResolverError as exc:
            self._set_status(str(exc))
            self._show_error(str(exc))

    def _on_clear(self) -> None:
        """
        Clear current PAI certificate file selection.
        """
        self.load_path(None)

    def _set_status(self, message: str) -> None:
        """
        Update status message label.
        """
        self._status_label.configure(text=message)

    def _show_error(self, message: str) -> None:
        """
        Show an error message popup.
        """
        messagebox.showerror("PAI Certificate Error", message)