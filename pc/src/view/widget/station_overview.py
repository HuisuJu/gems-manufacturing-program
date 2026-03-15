from __future__ import annotations

import customtkinter as ctk

from logger import Logger, LogLevel
from provision.reporter import ProvisionReporter
from system import Settings
from system.type import MODEL_NAME_KEY, STATION_ID_KEY, ModelName


_WIDGET_CORNER_RADIUS = 10
_WIDGET_BORDER_WIDTH = 2

_OUTER_TOP_PADY = (10, 0)

_DESCRIPTION_PADX = 16
_DESCRIPTION_PADY = (20, 8)

_MODEL_NAME_PADX = 16
_MODEL_NAME_PADY = (8, 12)

_INFO_PADX = 16
_INFO_PADY = (0, 16)

_INFO_ROW_GAP = 6


class StationOverviewWidget(ctk.CTkFrame):
    """Read-only widget showing station identity and provisioning statistics."""

    def __init__(
        self,
        parent: ctk.CTkFrame,
        **kwargs,
    ) -> None:
        super().__init__(parent, fg_color="transparent", **kwargs)

        self._compose()
        self.invalidate()

    def _compose(self) -> None:
        """Compose widget layout."""
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self._body = ctk.CTkFrame(
            self,
            border_width=_WIDGET_BORDER_WIDTH,
            corner_radius=_WIDGET_CORNER_RADIUS,
        )
        self._body.grid(
            row=0,
            column=0,
            sticky="nsew",
            pady=_OUTER_TOP_PADY,
        )

        self._title_label = ctk.CTkLabel(
            self,
            text="  Station Overview  ",
            font=ctk.CTkFont(size=16, weight="bold"),
            fg_color=self.cget("fg_color"),
        )
        self._title_label.place(relx=0.5, y=10, anchor="center")
        self._title_label.lift()

        self._body.grid_columnconfigure(0, weight=1)
        self._body.grid_rowconfigure(0, weight=0)
        self._body.grid_rowconfigure(1, weight=1)
        self._body.grid_rowconfigure(2, weight=0)

        self._description_label = ctk.CTkLabel(
            self._body,
            text="Current model, station, and accumulated provisioning results.",
            font=ctk.CTkFont(size=13),
            text_color=("gray45", "gray65"),
            anchor="w",
            justify="left",
            wraplength=300,
        )
        self._description_label.grid(
            row=0,
            column=0,
            padx=_DESCRIPTION_PADX,
            pady=_DESCRIPTION_PADY,
            sticky="ew",
        )

        self._model_name_label = ctk.CTkLabel(
            self._body,
            text="-",
            font=ctk.CTkFont(size=30, weight="bold"),
            anchor="center",
            justify="center",
        )
        self._model_name_label.grid(
            row=1,
            column=0,
            padx=_MODEL_NAME_PADX,
            pady=_MODEL_NAME_PADY,
            sticky="nsew",
        )

        self._info_frame = ctk.CTkFrame(self._body, fg_color="transparent")
        self._info_frame.grid(
            row=2,
            column=0,
            padx=_INFO_PADX,
            pady=_INFO_PADY,
            sticky="ew",
        )
        self._info_frame.grid_columnconfigure(0, weight=1)
        self._info_frame.grid_columnconfigure(1, weight=0)

        self._station_key_label = ctk.CTkLabel(
            self._info_frame,
            text="Station",
            anchor="w",
        )
        self._station_key_label.grid(
            row=0,
            column=0,
            padx=0,
            pady=(0, _INFO_ROW_GAP),
            sticky="w",
        )

        self._station_value_label = ctk.CTkLabel(
            self._info_frame,
            text="-",
            anchor="e",
            font=ctk.CTkFont(weight="bold"),
        )
        self._station_value_label.grid(
            row=0,
            column=1,
            padx=0,
            pady=(0, _INFO_ROW_GAP),
            sticky="e",
        )

        self._success_key_label = ctk.CTkLabel(
            self._info_frame,
            text="Success",
            anchor="w",
        )
        self._success_key_label.grid(
            row=1,
            column=0,
            padx=0,
            pady=(0, _INFO_ROW_GAP),
            sticky="w",
        )

        self._success_value_label = ctk.CTkLabel(
            self._info_frame,
            text="0",
            anchor="e",
            font=ctk.CTkFont(weight="bold"),
        )
        self._success_value_label.grid(
            row=1,
            column=1,
            padx=0,
            pady=(0, _INFO_ROW_GAP),
            sticky="e",
        )

        self._error_key_label = ctk.CTkLabel(
            self._info_frame,
            text="Error",
            anchor="w",
        )
        self._error_key_label.grid(
            row=2,
            column=0,
            padx=0,
            pady=(0, _INFO_ROW_GAP),
            sticky="w",
        )

        self._error_value_label = ctk.CTkLabel(
            self._info_frame,
            text="0",
            anchor="e",
            font=ctk.CTkFont(weight="bold"),
        )
        self._error_value_label.grid(
            row=2,
            column=1,
            padx=0,
            pady=(0, _INFO_ROW_GAP),
            sticky="e",
        )

        self._total_key_label = ctk.CTkLabel(
            self._info_frame,
            text="Total",
            anchor="w",
        )
        self._total_key_label.grid(
            row=3,
            column=0,
            padx=0,
            pady=0,
            sticky="w",
        )

        self._total_value_label = ctk.CTkLabel(
            self._info_frame,
            text="0",
            anchor="e",
            font=ctk.CTkFont(weight="bold"),
        )
        self._total_value_label.grid(
            row=3,
            column=1,
            padx=0,
            pady=0,
            sticky="e",
        )

    def invalidate(self) -> None:
        """Reload displayed values from settings and reporter stats."""
        model_value = Settings.get(MODEL_NAME_KEY)
        if not model_value:
            model_text = "-"
        else:
            try:
                model_text = ModelName(model_value).value.upper()
            except ValueError:
                model_text = str(model_value).upper()

        station_value = Settings.get(STATION_ID_KEY)
        if station_value is None:
            station_text = "-"
        else:
            station_text = str(station_value).strip() or "-"

        self._model_name_label.configure(text=model_text)
        self._station_value_label.configure(text=station_text)

        try:
            stats = ProvisionReporter.get_stats()
        except Exception as exc:
            Logger.write(
                LogLevel.WARNING,
                f"Failed to read provisioning stats: {exc}",
            )
            self._success_value_label.configure(text="0")
            self._error_value_label.configure(text="0")
            self._total_value_label.configure(text="0")
            return

        self._success_value_label.configure(text=str(stats.success_count))
        self._error_value_label.configure(text=str(stats.error_count))
        self._total_value_label.configure(text=str(stats.total_count))
