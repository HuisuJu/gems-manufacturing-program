from __future__ import annotations

from pathlib import Path

from tkinter import filedialog, messagebox

import customtkinter as ctk

import storage


class DacPoolResolverFrame(ctk.CTkFrame):
    """Widget for selecting and loading a DAC pool folder."""

    def __init__(self, master, **kwargs) -> None:
        super().__init__(master, **kwargs)

        self._current_path: Path | None = None

        self.grid_columnconfigure(1, weight=1)

        self._title_label = ctk.CTkLabel(
            self,
            text="DAC Pool Folder",
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
            text="Folder",
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

        self._summary_frame = ctk.CTkFrame(self)
        self._summary_frame.grid(
            row=3,
            column=0,
            columnspan=3,
            sticky="ew",
            padx=12,
            pady=6,
        )
        self._summary_frame.grid_columnconfigure((0, 1, 2, 3), weight=1)

        self._total_label = ctk.CTkLabel(
            self._summary_frame,
            text="Total: 0",
            anchor="center",
        )
        self._total_label.grid(
            row=0,
            column=0,
            sticky="ew",
            padx=8,
            pady=10,
        )

        self._ready_label = ctk.CTkLabel(
            self._summary_frame,
            text="Ready: 0",
            anchor="center",
        )
        self._ready_label.grid(
            row=0,
            column=1,
            sticky="ew",
            padx=8,
            pady=10,
        )

        self._consumed_label = ctk.CTkLabel(
            self._summary_frame,
            text="Consumed: 0",
            anchor="center",
        )
        self._consumed_label.grid(
            row=0,
            column=2,
            sticky="ew",
            padx=8,
            pady=10,
        )

        self._error_label = ctk.CTkLabel(
            self._summary_frame,
            text="Error: 0",
            anchor="center",
        )
        self._error_label.grid(
            row=0,
            column=3,
            sticky="ew",
            padx=8,
            pady=10,
        )

        self._status_label = ctk.CTkLabel(
            self,
            text="No DAC folder loaded.",
            anchor="w",
            justify="left",
            wraplength=700,
        )
        self._status_label.grid(
            row=4,
            column=0,
            columnspan=3,
            sticky="ew",
            padx=12,
            pady=(6, 12),
        )

    @property

    def current_path(self) -> Path | None:
        """Return current DAC folder path."""
        return self._current_path

    def load_path(self, path: Path | None) -> None:
        """Load DAC folder path and refresh widget state."""
        if path is None:
            storage.dac_pool_store.load(None)
            self._current_path = None
            self._path_entry.delete(0, "end")
            self._update_inventory_labels(
                storage.DacInventoryReport(total=0, ready=0, consumed=0, error=0)
            )
            self._set_status("No DAC folder loaded.")
            return

        storage.dac_pool_store.load(path)
        self._current_path = path.resolve()

        self._path_entry.delete(0, "end")
        self._path_entry.insert(0, str(self._current_path))

        report = storage.dac_pool_store.get_inventory_report()
        self._update_inventory_labels(report)
        self._set_status(f"DAC folder loaded successfully: {self._current_path}")

    def _on_browse(self) -> None:
        """Open folder picker and fill the path entry."""
        selected = filedialog.askdirectory(
            title="Select DAC Pool Folder",
            mustexist=True,
        )
        if not selected:
            return

        self._path_entry.delete(0, "end")
        self._path_entry.insert(0, selected)

    def _on_load(self) -> None:
        """Load folder from the path entry."""
        raw_path = self._path_entry.get().strip()
        if not raw_path:
            self._show_error("Please select a DAC folder first.")
            return

        try:
            self.load_path(Path(raw_path))
        except (
            storage.AttestationStoreConfigurationError,
            storage.AttestationStoreError,
        ) as exc:
            self._update_inventory_labels(
                storage.DacInventoryReport(total=0, ready=0, consumed=0, error=0)
            )
            self._set_status(str(exc))
            self._show_error(str(exc))

    def _on_refresh(self) -> None:
        """Reload current DAC folder."""
        if self._current_path is None:
            self._show_error("There is no DAC folder to refresh.")
            return

        try:
            self.load_path(self._current_path)
        except (
            storage.AttestationStoreConfigurationError,
            storage.AttestationStoreError,
        ) as exc:
            self._update_inventory_labels(
                storage.DacInventoryReport(total=0, ready=0, consumed=0, error=0)
            )
            self._set_status(str(exc))
            self._show_error(str(exc))

    def _on_clear(self) -> None:
        """Clear DAC folder selection and reset UI state."""
        try:
            self.load_path(None)
        except (
            storage.AttestationStoreConfigurationError,
            storage.AttestationStoreError,
        ) as exc:
            self._set_status(str(exc))
            self._show_error(str(exc))

    def _update_inventory_labels(self, report: storage.DacInventoryReport) -> None:
        """Update inventory summary labels."""
        self._total_label.configure(text=f"Total: {report.total}")
        self._ready_label.configure(text=f"Ready: {report.ready}")
        self._consumed_label.configure(text=f"Consumed: {report.consumed}")
        self._error_label.configure(text=f"Error: {report.error}")

    def _set_status(self, message: str) -> None:
        """Set status message."""
        self._status_label.configure(text=message)

    def _show_error(self, message: str) -> None:
        """Show error popup."""
        messagebox.showerror("DAC Pool Error", message)
