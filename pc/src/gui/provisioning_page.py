import customtkinter as ctk
import webbrowser
from datetime import datetime
from tkinter import filedialog

from stream import SerialManager
from session import Session
from logger import Logger, LogLevel

from gui.serial_widget import SerialWidget
from gui.log_widget import LogWidget
from gui.provisioning_control_widget import (
    ProvisioningControlWidget,
    WorkerIndicatorState,
)


class ProvisioningPage(ctk.CTkFrame):
    NUM_COLUMNS = 2
    NUM_ROWS = 2

    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)

        self._outer_margin = 20
        self._card_gap = 12

        self.grid_columnconfigure(0, weight=0)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=0)
        self.grid_rowconfigure(1, weight=1)

        self._qr_code_url: str = ""

        self._serial_manager = SerialManager(Session.on_serial_frame)
        Session.bind_serial(self._serial_manager)

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

        self._serial_widget = SerialWidget(self._left_2x2_panel, self._serial_manager)
        self._serial_widget.grid(
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

        self._empty_widget = self._create_titled_card(
            self._left_2x2_panel,
            title="empty",
            row=1,
            column=0,
            padx=(0, self._card_gap),
            pady=(0, 0),
        )
        self._empty_widget.grid_columnconfigure(0, weight=1)
        self._empty_widget.grid_rowconfigure(1, weight=1)

        self._log_management_widget = self._create_titled_card(
            self._left_2x2_panel,
            title="Log Management",
            row=1,
            column=1,
            padx=(0, 0),
            pady=(0, 0),
        )
        self._log_management_widget.grid_columnconfigure(0, weight=1)
        self._log_management_widget.grid_rowconfigure(1, weight=1)

        self._save_log_button = ctk.CTkButton(
            self._log_management_widget,
            text="Save Log",
            command=self._on_save_log,
            height=34,
        )
        self._save_log_button.grid(row=1, column=0, padx=16, pady=(30, 8), sticky="ew")

        self._save_log_status = ctk.CTkLabel(
            self._log_management_widget,
            text="Ready",
            font=ctk.CTkFont(size=12),
            anchor="w",
        )
        self._save_log_status.grid(row=2, column=0, padx=16, pady=(0, 12), sticky="ew")

        self._provisioning_control_widget = ProvisioningControlWidget(self)
        self._provisioning_control_widget.grid(
            row=0,
            column=1,
            padx=(self._card_gap, self._outer_margin),
            pady=(8, 12),
            sticky="nsew",
        )

        self._sync_serial_state_to_provisioning_ui()
        self._serial_manager.subscribe_event(self._on_serial_event)

        self._log_widget = LogWidget(self)
        self._log_widget.grid(
            row=1,
            column=0,
            columnspan=self.NUM_COLUMNS,
            padx=self._outer_margin,
            pady=(0, 20),
            sticky="nsew",
        )

    def _on_serial_event(self, _: str) -> None:
        self.after(0, self._sync_serial_state_to_provisioning_ui)

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

    def _sync_serial_state_to_provisioning_ui(self) -> None:
        connected = self._serial_manager.is_connected()
        if connected:
            self._provisioning_control_widget.set_worker_indicator_state(WorkerIndicatorState.IDLE)
            self._provisioning_control_widget.set_next_instruction(
                "Place the device on jig, then press START."
            )
            self._provisioning_control_widget.set_start_enabled(True)
            return

        self._provisioning_control_widget.set_worker_indicator_state(WorkerIndicatorState.DISCONNECTED)
        self._provisioning_control_widget.set_next_instruction(
            "Connect serial port first, then press START."
        )
        self._provisioning_control_widget.set_start_enabled(False)

    # External API (for future provisioning flow)
    def set_worker_indicator_idle(self) -> None:
        self._provisioning_control_widget.set_worker_indicator_state(WorkerIndicatorState.IDLE)

    def set_worker_indicator_success(self) -> None:
        self._provisioning_control_widget.set_worker_indicator_state(WorkerIndicatorState.SUCCESS)

    def set_worker_indicator_fail(self) -> None:
        self._provisioning_control_widget.set_worker_indicator_state(WorkerIndicatorState.FAIL)

    def set_worker_indicator_disconnected(self) -> None:
        self._provisioning_control_widget.set_worker_indicator_state(WorkerIndicatorState.DISCONNECTED)

    def set_next_operator_instruction(self, instruction: str) -> None:
        self._provisioning_control_widget.set_next_instruction(instruction)

    def on_external_user_event(self, name: str, message: str) -> None:
        self._provisioning_control_widget.handle_user_event(name=name, message=message)

    def set_qr_code_url(self, url: str) -> None:
        self._qr_code_url = str(url).strip()

    def _on_see_qr_code(self) -> None:
        if not self._qr_code_url:
            Logger.write(LogLevel.PROGRESS, "[USER_EVENT] See QR code clicked (URL is not configured yet)")
            return

        try:
            webbrowser.open(self._qr_code_url)
            Logger.write(LogLevel.PROGRESS, f"[USER_EVENT] Opened QR code URL: {self._qr_code_url}")
        except Exception as e:
            Logger.write(LogLevel.WARNING, f"Failed to open QR code URL ({type(e).__name__}: {e})")

    def _on_save_log(self) -> None:
        suggested_name = f"factory_provision_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
        file_path = filedialog.asksaveasfilename(
            title="Save Log",
            defaultextension=".log",
            initialfile=suggested_name,
            filetypes=[
                ("Log files", "*.log"),
                ("Text files", "*.txt"),
                ("All files", "*.*"),
            ],
        )
        if not file_path:
            self._save_log_status.configure(text="Save canceled")
            return

        try:
            content = self._log_widget.textbox.get("1.0", "end-1c")
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(content)
                if content and not content.endswith("\n"):
                    f.write("\n")

            self._save_log_status.configure(text=f"Saved: {file_path}")
            Logger.write(LogLevel.PROGRESS, f"Log saved to {file_path}")
        except Exception as e:
            self._save_log_status.configure(text="Save failed")
            Logger.write(LogLevel.ERROR, f"Log save failed ({type(e).__name__}: {e})")

    def _on_left_panel_resize(self, event) -> None:
        panel_width = max(int(event.width), 1)
        cell_size = max(120, min((panel_width - self._card_gap) // 2, 220))
        self._left_2x2_panel.grid_columnconfigure(0, minsize=cell_size)
        self._left_2x2_panel.grid_columnconfigure(1, minsize=cell_size)
        self._left_2x2_panel.grid_rowconfigure(0, minsize=cell_size)
        self._left_2x2_panel.grid_rowconfigure(1, minsize=cell_size)