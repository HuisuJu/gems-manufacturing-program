from __future__ import annotations

import webbrowser

import customtkinter as ctk

from logger import Logger, LogLevel
from settings import SettingsItem, settings as app_settings
from stream import SerialStream

from .view import (
    LogBoxView,
    LogSettingsView,
    ProvisioningView,
    SerialView,
)


class ProvisioningFrame(ctk.CTkFrame):
    NUM_COLUMNS = 2
    NUM_ROWS = 2

    def __init__(
        self,
        master: ctk.CTkFrame,
        serial_manager: SerialStream,
        **kwargs,
    ) -> None:
        super().__init__(master, **kwargs)

        self._outer_margin = 20
        self._card_gap = 12
        self._serial_manager = serial_manager
        self._qr_code_url: str = ""

        self.grid_columnconfigure(0, weight=0)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=0)
        self.grid_rowconfigure(1, weight=1)

        self._left_2x2_panel = ctk.CTkFrame(self, fg_color="transparent")
        self._left_2x2_panel.grid(
            row=0,
            column=0,
            padx=(self._outer_margin, self._card_gap),
            pady=(8, 12),
            sticky="nw",
        )
        self._left_2x2_panel.grid_columnconfigure(0, weight=1, uniform="left_box")
        self._left_2x2_panel.grid_columnconfigure(1, weight=1, uniform="left_box")
        self._left_2x2_panel.grid_rowconfigure(0, weight=1, uniform="left_box")
        self._left_2x2_panel.grid_rowconfigure(1, weight=1, uniform="left_box")
        self._left_2x2_panel.bind("<Configure>", self._on_left_panel_resize)

        self.serial_view = SerialView(self._left_2x2_panel, self._serial_manager)
        self.serial_view.grid(
            row=0,
            column=0,
            padx=(0, self._card_gap),
            pady=(0, self._card_gap),
            sticky="nsew",
        )

        self._provision_result_widget = self._create_titled_card(
            self._left_2x2_panel,
            title="Provision Result",
            row=0,
            column=1,
            padx=(0, 0),
            pady=(0, self._card_gap),
        )
        self._provision_result_widget.grid_columnconfigure(0, weight=1)
        self._provision_result_widget.grid_rowconfigure(1, weight=1)

        self._see_qr_button = ctk.CTkButton(
            self._provision_result_widget,
            text="See QR code",
            command=self._on_see_qr_code,
            height=34,
        )
        self._see_qr_button.grid(row=1, column=0, padx=16, pady=(30, 14), sticky="ew")

        self._target_widget = self._create_titled_card(
            self._left_2x2_panel,
            title="Target",
            row=1,
            column=0,
            padx=(0, self._card_gap),
            pady=(0, 0),
        )
        self._target_widget.grid_columnconfigure(0, weight=1)
        self._target_widget.grid_rowconfigure(0, weight=0)
        self._target_widget.grid_rowconfigure(1, weight=1)

        self._target_label = ctk.CTkLabel(
            self._target_widget,
            text="Provisioning target model",
            anchor="w",
            justify="left",
        )
        self._target_label.grid(
            row=0,
            column=0,
            padx=16,
            pady=(24, 8),
            sticky="ew",
        )

        self._target_status_label = ctk.CTkLabel(
            self._target_widget,
            text="",
            font=ctk.CTkFont(size=12),
            anchor="w",
            justify="left",
            wraplength=220,
        )
        self._target_status_label.grid(
            row=1,
            column=0,
            padx=16,
            pady=(0, 12),
            sticky="ew",
        )

        self._log_management_widget = self._create_titled_card(
            self._left_2x2_panel,
            title="Log Management",
            row=1,
            column=1,
            padx=(0, 0),
            pady=(0, 0),
        )
        self._log_management_widget.grid_columnconfigure(0, weight=1)
        self._log_management_widget.grid_rowconfigure(0, weight=1)

        self.log_box_view = LogBoxView(self)
        self.log_box_view.grid(
            row=1,
            column=0,
            columnspan=self.NUM_COLUMNS,
            padx=self._outer_margin,
            pady=(0, 20),
            sticky="nsew",
        )

        self.log_settings_view = LogSettingsView(
            self._log_management_widget,
            log_box_view=self.log_box_view,
        )
        self.log_settings_view.grid(
            row=0,
            column=0,
            padx=8,
            pady=(18, 8),
            sticky="nsew",
        )

        self.provisioning_view = ProvisioningView(self)
        self.provisioning_view.grid(
            row=0,
            column=1,
            padx=(self._card_gap, self._outer_margin),
            pady=(8, 12),
            sticky="nsew",
        )

        self._serial_manager.subscribe_event(self._on_serial_event)

        self.after(0, self._refresh_target_status)

    def refresh_target_status(self) -> None:
        """
        Refresh the target model information shown in the target card.
        """
        self._refresh_target_status()

    def set_qr_code_url(self, url: str) -> None:
        """
        Set the QR code URL opened by the result button.
        """
        self._qr_code_url = str(url).strip()

    def _refresh_target_status(self) -> None:
        model_name = app_settings.get(SettingsItem.MODEL_NAME)

        if model_name is None:
            self._target_status_label.configure(
                text="Target model is not configured yet."
            )
            return

        self._target_status_label.configure(
            text=f"Current target: {getattr(model_name, 'value', model_name)}"
        )

    def _on_serial_event(self, event_name: str) -> None:
        Logger.write(LogLevel.PROGRESS, f"[SERIAL] event={event_name}")

    def _create_titled_card(
        self,
        parent: ctk.CTkFrame,
        title: str,
        row: int,
        column: int,
        padx: tuple[int, int],
        pady: tuple[int, int],
    ) -> ctk.CTkFrame:
        container = ctk.CTkFrame(parent, fg_color="transparent")
        container.grid(row=row, column=column, padx=padx, pady=pady, sticky="nsew")
        container.grid_columnconfigure(0, weight=1)
        container.grid_rowconfigure(0, weight=1)

        body = ctk.CTkFrame(container, border_width=2, corner_radius=10)
        body.grid(row=0, column=0, sticky="nsew", pady=(10, 0))

        title_label = ctk.CTkLabel(
            container,
            text=f"  {title}  ",
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color=self.cget("fg_color"),
        )
        title_label.place(relx=0.5, y=10, anchor="center")
        title_label.lift()
        return body

    def _on_see_qr_code(self) -> None:
        if not self._qr_code_url:
            Logger.write(
                LogLevel.PROGRESS,
                "[USER_EVENT] See QR code clicked (URL is not configured yet)",
            )
            return

        try:
            webbrowser.open(self._qr_code_url)
            Logger.write(
                LogLevel.PROGRESS,
                f"[USER_EVENT] Opened QR code URL: {self._qr_code_url}",
            )
        except Exception as exc:
            Logger.write(
                LogLevel.WARNING,
                f"Failed to open QR code URL ({type(exc).__name__}: {exc})",
            )

    def _on_left_panel_resize(self, event) -> None:
        panel_width = max(int(event.width), 1)
        cell_size = max(120, min((panel_width - self._card_gap) // 2, 220))
        self._left_2x2_panel.grid_columnconfigure(0, minsize=cell_size)
        self._left_2x2_panel.grid_columnconfigure(1, minsize=cell_size)
        self._left_2x2_panel.grid_rowconfigure(0, minsize=cell_size)
        self._left_2x2_panel.grid_rowconfigure(1, minsize=cell_size)

    def destroy(self) -> None:
        self._serial_manager.unsubscribe_event(self._on_serial_event)
        super().destroy()