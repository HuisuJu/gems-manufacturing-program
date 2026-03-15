from __future__ import annotations

import customtkinter as ctk

from ..widget import (
    LogBoxWidget,
    LogSettingWidget,
    ProvisionerWidget,
    SerialSettingWidget,
    StationOverviewWidget,
)


class ProvisioningFrame(ctk.CTkFrame):
    NUM_COLUMNS = 2
    _LEFT_PANEL_UNIFORM = "left_panel_widgets"

    def __init__(
        self,
        master: ctk.CTkFrame,
        **kwargs,
    ) -> None:
        super().__init__(master, **kwargs)

        self._outer_margin = 20
        self._section_gap = 12
        self._left_panel_width = 360
        self._log_box_height = 180

        self._compose()

    def _compose(self) -> None:
        """Compose frame layout and child widgets."""
        self._compose_layout()
        self._compose_widgets()

    def _compose_layout(self) -> None:
        """Configure the main layout."""
        self.grid_columnconfigure(0, weight=0, minsize=self._left_panel_width)
        self.grid_columnconfigure(1, weight=1)

        self.grid_rowconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=0, minsize=self._log_box_height)

    def _compose_widgets(self) -> None:
        """Create child widgets."""
        self._compose_left_panel()
        self._compose_provisioning_widget()
        self._compose_log_box_widget()

    def _compose_left_panel(self) -> None:
        """Create the left stacked widgets panel."""
        self._left_panel = ctk.CTkFrame(
            self,
            fg_color="transparent",
            width=self._left_panel_width,
        )
        self._left_panel.grid(
            row=0,
            column=0,
            padx=(self._outer_margin, self._section_gap),
            pady=(12, 12),
            sticky="nsew",
        )
        self._left_panel.grid_propagate(False)

        self._left_panel.grid_columnconfigure(0, weight=1)
        self._left_panel.grid_rowconfigure(
            0, weight=1, uniform=self._LEFT_PANEL_UNIFORM
        )
        self._left_panel.grid_rowconfigure(
            1, weight=1, uniform=self._LEFT_PANEL_UNIFORM
        )
        self._left_panel.grid_rowconfigure(
            2, weight=1, uniform=self._LEFT_PANEL_UNIFORM
        )

        self.log_box_widget = LogBoxWidget(self)
        self.log_box_widget.configure(height=self._log_box_height)

        self.station_overview_view = StationOverviewWidget(self._left_panel)
        self.station_overview_view.grid(
            row=0,
            column=0,
            padx=0,
            pady=(0, self._section_gap),
            sticky="nsew",
        )

        self.serial_view = SerialSettingWidget(self._left_panel)
        self.serial_view.grid(
            row=1,
            column=0,
            padx=0,
            pady=(0, self._section_gap),
            sticky="nsew",
        )

        self.log_settings_view = LogSettingWidget(
            self._left_panel,
            log_box_widget=self.log_box_widget,
        )
        self.log_settings_view.grid(
            row=2,
            column=0,
            padx=0,
            pady=0,
            sticky="nsew",
        )

    def _compose_provisioning_widget(self) -> None:
        """Create the main provisioning widget."""
        self.provisioning_view = ProvisionerWidget(self)
        self.provisioning_view.grid(
            row=0,
            column=1,
            padx=(0, self._outer_margin),
            pady=(12, 12),
            sticky="nsew",
        )

    def _compose_log_box_widget(self) -> None:
        """Create the bottom log box."""
        self.log_box_widget.grid(
            row=1,
            column=0,
            columnspan=self.NUM_COLUMNS,
            padx=self._outer_margin,
            pady=(0, 20),
            sticky="nsew",
        )
