from __future__ import annotations

from pathlib import Path

import customtkinter as ctk
from tkinter import filedialog

from factory_data import FactoryDataPoolManager, FactoryDataPoolManagerError
from provision import ProvisionReporter


class PathFinderWidget(ctk.CTkFrame):
    """
    UI widget for configuring important application folders.

    This widget directly references shared application logic objects.

    Supported paths:
        - factory data pool folder
        - provision report output folder
    """

    def __init__(self, parent: ctk.CTkFrame, **kwargs):
        super().__init__(parent, fg_color="transparent", **kwargs)

        self._pool_manager = FactoryDataPoolManager()
        self._reporter = ProvisionReporter()

        self.grid_columnconfigure(0, weight=1)

        self._frame = ctk.CTkFrame(self, border_width=2, corner_radius=10)
        self._frame.grid(row=0, column=0, sticky="nsew", pady=(10, 0))
        self._frame.grid_columnconfigure(0, weight=1)

        self._title_label = ctk.CTkLabel(
            self,
            text="  Paths  ",
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color=self.master.cget("fg_color"),
        )
        self._title_label.place(relx=0.5, y=10, anchor="center")
        self._title_label.lift()

        self._description_label = ctk.CTkLabel(
            self._frame,
            text=(
                "Configure folders required by the factory provisioning tool. "
                "Both paths can be changed later."
            ),
            anchor="w",
            justify="left",
            wraplength=520,
            font=ctk.CTkFont(size=12),
        )
        self._description_label.grid(
            row=0,
            column=0,
            padx=20,
            pady=(24, 16),
            sticky="ew",
        )

        self._factory_section = self._create_path_section(
            row=1,
            title="Factory Data Pool",
            description="Folder containing provisioning JSON files.",
            select_button_text="Browse Factory Data Pool",
            clear_button_text="Clear",
            select_command=self._on_select_factory_data_pool_clicked,
            clear_command=self._on_clear_factory_data_pool_clicked,
        )

        self._report_section = self._create_path_section(
            row=2,
            title="Provision Report Output",
            description="Folder where provisioning result report files will be saved.",
            select_button_text="Browse Report Folder",
            clear_button_text="Reset",
            select_command=self._on_select_report_output_clicked,
            clear_command=self._on_reset_report_output_clicked,
        )

        self._status_label = ctk.CTkLabel(
            self._frame,
            text="Ready",
            anchor="w",
            justify="left",
            font=ctk.CTkFont(size=12),
            text_color="gray70",
        )
        self._status_label.grid(
            row=3,
            column=0,
            padx=20,
            pady=(0, 16),
            sticky="ew",
        )

        self._load_initial_values()

    def _load_initial_values(self) -> None:
        """
        Load initial values from shared application logic objects.
        """
        current_pool_path = self._pool_manager.get_pool_path()
        if current_pool_path is not None:
            self.set_factory_data_pool_path(current_pool_path)
        else:
            self.clear_factory_data_pool_path()

        current_report_dir = self._reporter.get_report_dir()
        self.set_report_output_path(current_report_dir)

    def set_factory_data_pool_path(self, path: str | Path) -> None:
        """
        Update the displayed factory data pool path.
        """
        self._factory_section["path_label"].configure(text=str(path))

    def clear_factory_data_pool_path(self) -> None:
        """
        Reset the displayed factory data pool path.
        """
        self._factory_section["path_label"].configure(text="No folder selected")

    def set_report_output_path(self, path: str | Path) -> None:
        """
        Update the displayed report output path.
        """
        self._report_section["path_label"].configure(text=str(path))

    def clear_report_output_path(self) -> None:
        """
        Reset the displayed report output path.
        """
        self._report_section["path_label"].configure(text="No folder selected")

    def _create_path_section(
        self,
        *,
        row: int,
        title: str,
        description: str,
        select_button_text: str,
        clear_button_text: str,
        select_command,
        clear_command,
    ) -> dict[str, ctk.CTkBaseClass]:
        """
        Create one styled path configuration section.
        """
        section = ctk.CTkFrame(self._frame, corner_radius=10)
        section.grid(row=row, column=0, padx=16, pady=(0, 14), sticky="ew")
        section.grid_columnconfigure(0, weight=1)
        section.grid_columnconfigure(1, weight=0)
        section.grid_columnconfigure(2, weight=0)

        title_label = ctk.CTkLabel(
            section,
            text=title,
            font=ctk.CTkFont(size=15, weight="bold"),
            anchor="w",
        )
        title_label.grid(
            row=0,
            column=0,
            columnspan=3,
            padx=16,
            pady=(14, 2),
            sticky="ew",
        )

        description_label = ctk.CTkLabel(
            section,
            text=description,
            font=ctk.CTkFont(size=12),
            anchor="w",
            justify="left",
            text_color="gray70",
            wraplength=480,
        )
        description_label.grid(
            row=1,
            column=0,
            columnspan=3,
            padx=16,
            pady=(0, 10),
            sticky="ew",
        )

        path_label = ctk.CTkLabel(
            section,
            text="No folder selected",
            anchor="w",
            justify="left",
            wraplength=480,
            corner_radius=8,
            fg_color=("gray92", "gray18"),
            padx=12,
            pady=10,
            font=ctk.CTkFont(size=12),
        )
        path_label.grid(
            row=2,
            column=0,
            columnspan=3,
            padx=16,
            pady=(0, 12),
            sticky="ew",
        )

        select_button = ctk.CTkButton(
            section,
            text=select_button_text,
            height=34,
            command=select_command,
        )
        select_button.grid(row=3, column=1, padx=(0, 8), pady=(0, 14), sticky="e")

        clear_button = ctk.CTkButton(
            section,
            text=clear_button_text,
            height=34,
            width=72,
            command=clear_command,
            fg_color=("gray70", "gray30"),
            hover_color=("gray60", "gray25"),
        )
        clear_button.grid(row=3, column=2, padx=(0, 16), pady=(0, 14), sticky="e")

        return {
            "section": section,
            "title_label": title_label,
            "description_label": description_label,
            "path_label": path_label,
            "select_button": select_button,
            "clear_button": clear_button,
        }

    def _on_select_factory_data_pool_clicked(self) -> None:
        """
        Open folder selection dialog for the factory data pool path and apply it
        directly to FactoryDataPoolManager.
        """
        selected = filedialog.askdirectory(title="Select Factory Data Pool Folder")
        if not selected:
            return

        try:
            self._pool_manager.set_pool_path(selected)
            self.set_factory_data_pool_path(selected)
            self._set_status("Factory data pool folder updated.")
        except FactoryDataPoolManagerError as exc:
            self._set_status(str(exc), is_error=True)
        except Exception as exc:
            self._set_status(
                f"Failed to update factory data pool folder: {type(exc).__name__}: {exc}",
                is_error=True,
            )

    def _on_clear_factory_data_pool_clicked(self) -> None:
        """
        Clear the factory data pool path directly in FactoryDataPoolManager.
        """
        try:
            self._pool_manager.set_pool_path(None)
            self.clear_factory_data_pool_path()
            self._set_status("Factory data pool folder cleared.")
        except FactoryDataPoolManagerError as exc:
            self._set_status(str(exc), is_error=True)
        except Exception as exc:
            self._set_status(
                f"Failed to clear factory data pool folder: {type(exc).__name__}: {exc}",
                is_error=True,
            )

    def _on_select_report_output_clicked(self) -> None:
        """
        Open folder selection dialog for the report output path and apply it
        directly to the shared ProvisionReporter.
        """
        selected = filedialog.askdirectory(title="Select Provision Report Output Folder")
        if not selected:
            return

        try:
            self._reporter.set_report_dir(selected)
            self.set_report_output_path(selected)
            self._set_status("Provision report output folder updated.")
        except Exception as exc:
            self._set_status(
                f"Failed to update report output folder: {type(exc).__name__}: {exc}",
                is_error=True,
            )

    def _on_reset_report_output_clicked(self) -> None:
        """
        Reset the report output folder to the shared reporter default directory.
        """
        try:
            self._reporter.reset_report_dir_to_default()
            default_dir = self._reporter.get_report_dir()
            self.set_report_output_path(default_dir)
            self._set_status("Provision report output folder reset to default.")
        except Exception as exc:
            self._set_status(
                f"Failed to reset report output folder: {type(exc).__name__}: {exc}",
                is_error=True,
            )

    def _set_status(self, text: str, *, is_error: bool = False) -> None:
        """
        Update the widget status line.
        """
        self._status_label.configure(
            text=text,
            text_color=("red" if is_error else "gray70"),
        )