from __future__ import annotations

import customtkinter as ctk

from logger import Logger, LogLevel
from system import Settings, SettingsItem
from stream import SerialStream

from ..dialog import QrCodeView

from ..widget import (
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
        self._left_panel_width = 820
        self._left_panel_height = 340
        self._serial_manager = serial_manager

        self.grid_columnconfigure(0, weight=0)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=0)
        self.grid_rowconfigure(1, weight=1)

        self._left_2x2_panel = ctk.CTkFrame(self, fg_color="transparent")
        self._left_2x2_panel.configure(
            width=self._left_panel_width,
            height=self._left_panel_height,
        )
        self._left_2x2_panel.grid_propagate(False)
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
        self._provision_result_widget.grid_rowconfigure(0, weight=0)
        self._provision_result_widget.grid_rowconfigure(1, weight=1)

        self._provision_result_label = ctk.CTkLabel(
            self._provision_result_widget,
            text="Provisioning result summary",
            anchor="w",
            justify="left",
        )
        self._provision_result_label.grid(
            row=0,
            column=0,
            padx=16,
            pady=(24, 8),
            sticky="ew",
        )

        self._provision_result_status_label = ctk.CTkLabel(
            self._provision_result_widget,
            text="No provisioning result is available yet.",
            font=ctk.CTkFont(size=12),
            anchor="w",
            justify="left",
            wraplength=220,
        )
        self._provision_result_status_label.grid(
            row=1,
            column=0,
            padx=16,
            pady=(0, 12),
            sticky="ew",
        )

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

        self.qr_code_view = QrCodeView(self)

        self._serial_manager.subscribe_event(self._on_serial_event)

        self.after(0, self._refresh_target_status)

    def refresh_target_status(self) -> None:
        """
        Refresh the target model information shown in the target card.
        """
        self._refresh_target_status()

    def set_provision_result_summary(self, text: str) -> None:
        """
        Update the provision result summary text shown in the result card.
        """
        self._provision_result_status_label.configure(text=text)

    def show_qr_code(
        self,
        payload: str,
        manual_code: str | None = None,
        *,
        auto_show: bool = True,
        title: str = "Matter QR Code",
    ) -> None:
        """
        Store and optionally show the latest QR code result.
        """
        self.qr_code_view.set_qr_code(
            payload=payload,
            manual_code=manual_code,
            auto_show=auto_show,
            title=title,
        )

        summary = "QR code is available."
        if manual_code:
            summary = f"QR code is available.\nManual pairing code: {manual_code}"

        self.set_provision_result_summary(summary)

    def clear_qr_code(self) -> None:
        """
        Clear the stored QR code result.
        """
        self.qr_code_view.clear_qr_code()
        self.set_provision_result_summary("No provisioning result is available yet.")

    def show_last_qr_code(self) -> bool:
        """
        Show the latest QR code popup.

        Returns:
            True if shown, otherwise False.
        """
        return self.qr_code_view.show_last_qr_code()

    def _refresh_target_status(self) -> None:
        model_name = Settings.get(SettingsItem.MODEL_NAME)

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

    def _on_left_panel_resize(self, event) -> None:
        panel_width = max(int(event.width), 1)
        panel_height = max(int(event.height), 1)
        width_based_size = (panel_width - self._card_gap) // 2
        height_based_size = (panel_height - self._card_gap) // 2
        cell_size = max(110, min(width_based_size, height_based_size, 145))
        self._left_2x2_panel.grid_columnconfigure(0, minsize=cell_size)
        self._left_2x2_panel.grid_columnconfigure(1, minsize=cell_size)
        self._left_2x2_panel.grid_rowconfigure(0, minsize=cell_size)
        self._left_2x2_panel.grid_rowconfigure(1, minsize=cell_size)

    def destroy(self) -> None:
        self._serial_manager.unsubscribe_event(self._on_serial_event)
        super().destroy()