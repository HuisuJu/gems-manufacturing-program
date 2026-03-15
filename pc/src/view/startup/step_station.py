from __future__ import annotations

from pathlib import Path
from tkinter import filedialog
from typing import Optional

import customtkinter as ctk

from system import REPORT_DIR_PATH_KEY, STATION_ID_KEY, Settings
from view.common.navigation.step import NavigationStep, ReadyCallback


_CARD_CORNER_RADIUS = 14
_CARD_BORDER_WIDTH = 1
_CARD_PADX = 20
_CARD_PADY_TOP = 18
_CARD_PADY_BOTTOM = 18

_LABEL_WIDTH = 170
_INPUT_HEIGHT = 40
_BROWSE_BUTTON_WIDTH = 110
_DESCRIPTION_WRAPLENGTH = 900


class StationIdCard(ctk.CTkFrame):
    """Card for station ID input."""

    def __init__(
        self,
        parent: ctk.CTkFrame,
        station_id_var: ctk.StringVar,
        **kwargs,
    ) -> None:
        super().__init__(
            parent,
            corner_radius=_CARD_CORNER_RADIUS,
            border_width=_CARD_BORDER_WIDTH,
            **kwargs,
        )

        self._station_id_var = station_id_var

        self.grid_columnconfigure(1, weight=1)

        self._title_label = ctk.CTkLabel(
            self,
            text="Station ID",
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

        self._entry = ctk.CTkEntry(
            self,
            textvariable=self._station_id_var,
            height=_INPUT_HEIGHT,
            font=ctk.CTkFont(size=13),
        )
        self._entry.grid(
            row=0,
            column=1,
            sticky="ew",
            padx=(0, _CARD_PADX),
            pady=(_CARD_PADY_TOP, 8),
        )

        self._description_label = ctk.CTkLabel(
            self,
            text="Use a short, unique station ID for logs, results, and records.",
            anchor="e",
            justify="right",
            wraplength=_DESCRIPTION_WRAPLENGTH,
            font=ctk.CTkFont(size=13),
            text_color=("gray45", "gray65"),
        )
        self._description_label.grid(
            row=1,
            column=0,
            columnspan=2,
            sticky="ew",
            padx=_CARD_PADX,
            pady=(0, _CARD_PADY_BOTTOM),
        )

    @property
    def value(self) -> str:
        """Return normalized station ID."""
        return self._station_id_var.get().strip()


class ReportDirectoryCard(ctk.CTkFrame):
    """Card for report directory selection."""

    def __init__(
        self,
        parent: ctk.CTkFrame,
        report_dir_path_var: ctk.StringVar,
        **kwargs,
    ) -> None:
        super().__init__(
            parent,
            corner_radius=_CARD_CORNER_RADIUS,
            border_width=_CARD_BORDER_WIDTH,
            **kwargs,
        )

        self._report_dir_path_var = report_dir_path_var

        self.grid_columnconfigure(1, weight=1)

        self._title_label = ctk.CTkLabel(
            self,
            text="Report Directory",
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

        self._entry = ctk.CTkEntry(
            self._input_frame,
            textvariable=self._report_dir_path_var,
            height=_INPUT_HEIGHT,
            font=ctk.CTkFont(size=13),
        )
        self._entry.grid(
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
            command=self._on_browse_clicked,
        )
        self._browse_button.grid(
            row=0,
            column=1,
            sticky="e",
        )

        self._description_label = ctk.CTkLabel(
            self,
            text="Choose an accessible folder for provisioning result files.",
            anchor="e",
            justify="right",
            wraplength=_DESCRIPTION_WRAPLENGTH,
            font=ctk.CTkFont(size=13),
            text_color=("gray45", "gray65"),
        )
        self._description_label.grid(
            row=1,
            column=0,
            columnspan=2,
            sticky="ew",
            padx=_CARD_PADX,
            pady=(0, _CARD_PADY_BOTTOM),
        )

    @property
    def value(self) -> Optional[Path]:
        """Return normalized report directory."""
        raw_value = self._report_dir_path_var.get().strip()
        if not raw_value:
            return None
        return Path(raw_value).expanduser()

    def _on_browse_clicked(self) -> None:
        """Open directory chooser dialog."""
        initial_dir = self._report_dir_path_var.get().strip() or None

        selected_dir = filedialog.askdirectory(
            title="Select Report Directory",
            initialdir=initial_dir,
        )
        if not selected_dir:
            return

        self._report_dir_path_var.set(str(Path(selected_dir).expanduser()))


class StationSetupStep(NavigationStep):
    """Startup step for station information configuration."""

    def __init__(
        self,
        parent: ctk.CTkFrame,
        on_ready: Optional[ReadyCallback] = None,
        **kwargs,
    ) -> None:
        super().__init__(parent, on_ready=on_ready, **kwargs)

        previous_station_id = Settings.get(STATION_ID_KEY)
        previous_report_dir_path = Settings.get(REPORT_DIR_PATH_KEY)

        self._station_id_var = ctk.StringVar(value=previous_station_id or "")
        self._report_dir_path_var = ctk.StringVar(value=previous_report_dir_path or "")

        self._build_ui()

        self._station_id_var.trace_add("write", self._on_input_changed)
        self._report_dir_path_var.trace_add("write", self._on_input_changed)

        self.is_ready = bool(self.station_id and self.report_directory is not None)

    def _build_ui(self) -> None:
        """Build step UI."""
        self.grid_columnconfigure(0, weight=1)

        self._title_label = ctk.CTkLabel(
            self,
            text="Station Information",
            anchor="w",
            font=ctk.CTkFont(size=35, weight="bold"),
        )
        self._title_label.grid(
            row=0,
            column=0,
            sticky="ew",
            pady=(0, 18),
        )

        self._subtitle_label = ctk.CTkLabel(
            self,
            text=(
                "Set the station ID and folder for provisioning result files."
            ),
            anchor="w",
            justify="left",
            font=ctk.CTkFont(size=14),
            text_color=("gray45", "gray65"),
        )
        self._subtitle_label.grid(
            row=1,
            column=0,
            sticky="ew",
            pady=(0, 20),
        )

        self._station_id_card = StationIdCard(
            self,
            station_id_var=self._station_id_var,
        )
        self._station_id_card.grid(
            row=2,
            column=0,
            sticky="ew",
            pady=(0, 14),
        )

        self._report_directory_card = ReportDirectoryCard(
            self,
            report_dir_path_var=self._report_dir_path_var,
        )
        self._report_directory_card.grid(
            row=3,
            column=0,
            sticky="ew",
        )

    @property
    def station_id(self) -> str:
        """Return normalized station ID."""
        return self._station_id_var.get().strip()

    @property
    def report_directory(self) -> Optional[Path]:
        """Return normalized report directory."""
        raw_value = self._report_dir_path_var.get().strip()
        if not raw_value:
            return None
        return Path(raw_value).expanduser()

    def commit(self) -> bool:
        """Persist station configuration."""
        if not self.is_ready:
            return False

        Settings.set(STATION_ID_KEY, self.station_id)
        Settings.set(REPORT_DIR_PATH_KEY, str(self.report_directory))
        return True

    def _on_input_changed(self, *_: object) -> None:
        """Update ready state when input changes."""
        self.is_ready = bool(self.station_id and self.report_directory is not None)
