import customtkinter as ctk
import webbrowser
from datetime import datetime
from tkinter import filedialog

from stream import SerialManager
from session import Session
from logger import Logger, LogLevel

from provision import (
    ProvisionDispatcher,
    ProvisionManager,
    ProvisionManagerEvent,
    ProvisionReporter,
)
from emulator.dispatcher import EmulatorDispatcher

from .serial_widget import SerialWidget
from .log_widget import LogWidget
from .control_widget import ProvisioningControlWidget


class ProvisioningPage(ctk.CTkFrame):
    NUM_COLUMNS = 2
    NUM_ROWS = 2

    TARGET_DOORLOCK = "doorlock"
    TARGET_THERMOSTAT = "thermostat"
    TARGET_EMULATOR = "emulator"

    EMULATOR_PORTS = [
        "doorlock_emulator",
        "thermostat_emulator",
    ]

    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)

        self._outer_margin = 20
        self._card_gap = 12

        self.grid_columnconfigure(0, weight=0)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=0)
        self.grid_rowconfigure(1, weight=1)

        self._qr_code_url: str = ""
        self._current_target_mode = ctk.StringVar(value=self.TARGET_EMULATOR)

        self._serial_manager = SerialManager(Session.on_serial_frame)
        Session.bind_serial(self._serial_manager)

        self._provision_manager = ProvisionManager()

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
        self._target_widget.grid_rowconfigure(1, weight=0)
        self._target_widget.grid_rowconfigure(2, weight=1)

        self._target_mode_label = ctk.CTkLabel(
            self._target_widget,
            text="Provisioning target mode",
            anchor="w",
            justify="left",
        )
        self._target_mode_label.grid(
            row=0,
            column=0,
            padx=16,
            pady=(24, 8),
            sticky="ew",
        )

        self._target_mode_menu = ctk.CTkOptionMenu(
            self._target_widget,
            values=[
                self.TARGET_DOORLOCK,
                self.TARGET_THERMOSTAT,
                self.TARGET_EMULATOR,
            ],
            variable=self._current_target_mode,
            command=self._on_target_mode_changed,
        )
        self._target_mode_menu.grid(
            row=1,
            column=0,
            padx=16,
            pady=(0, 10),
            sticky="ew",
        )

        self._target_mode_status = ctk.CTkLabel(
            self._target_widget,
            text="",
            font=ctk.CTkFont(size=12),
            anchor="w",
            justify="left",
            wraplength=220,
        )
        self._target_mode_status.grid(
            row=2,
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
        self._provisioning_control_widget.set_user_event_listener(
            self._on_provisioning_user_event
        )

        self._log_widget = LogWidget(self)
        self._log_widget.grid(
            row=1,
            column=0,
            columnspan=self.NUM_COLUMNS,
            padx=self._outer_margin,
            pady=(0, 20),
            sticky="nsew",
        )

        self._serial_manager.subscribe_event(self._on_serial_event)
        self._provision_manager.set_event_listener(self._on_provision_manager_event)

        self.after(0, self._initialize_provision_environment)

    def _initialize_provision_environment(self) -> None:
        """
        Initialize dispatcher selection and start the manager thread.
        """
        self._apply_target_mode(self._current_target_mode.get())
        self._provision_manager.start()

    def set_target_mode(self, target_mode: str) -> None:
        """
        Set the current target mode externally.

        This method is used by Window after the startup selection dialog.
        """
        normalized = str(target_mode).strip().lower()
        if normalized not in {
            self.TARGET_DOORLOCK,
            self.TARGET_THERMOSTAT,
            self.TARGET_EMULATOR,
        }:
            Logger.write(
                LogLevel.WARNING,
                f"[PROVISION] Ignored invalid target mode: {target_mode}",
            )
            return

        self._current_target_mode.set(normalized)
        self._apply_target_mode(normalized)

    def set_provision_dispatcher(self, dispatcher: ProvisionDispatcher) -> None:
        """
        Configure the active provision dispatcher.
        """
        self._provision_manager.set_dispatcher(dispatcher)

    def clear_provision_dispatcher(self) -> None:
        """
        Clear the active provision dispatcher.
        """
        self._provision_manager.set_dispatcher(None)

    def set_provision_reporter(self, reporter: ProvisionReporter) -> None:
        """
        Replace the default provision reporter.
        """
        self._provision_manager.set_reporter(reporter)

    def _on_target_mode_changed(self, selected_value: str) -> None:
        """
        Handle target mode selection changes from the UI.
        """
        self._apply_target_mode(selected_value)

    def _apply_target_mode(self, target_mode: str) -> None:
        """
        Apply the selected target mode by configuring an appropriate dispatcher
        and serial port source.
        """
        target_mode = str(target_mode).strip().lower()

        if target_mode == self.TARGET_EMULATOR:
            dispatcher = EmulatorDispatcher(
                initial_ready=True,
                dispatch_delay_sec=1.0,
                default_success=True,
            )
            self.set_provision_dispatcher(dispatcher)
            self._serial_widget.set_virtual_ports(self.EMULATOR_PORTS)
            self._target_mode_status.configure(
                text="Emulator dispatcher is active. Use *_emulator virtual ports."
            )
            Logger.write(
                LogLevel.PROGRESS,
                "[PROVISION] Target mode changed to emulator.",
            )
            return

        if target_mode == self.TARGET_DOORLOCK:
            self.clear_provision_dispatcher()
            self._serial_widget.clear_virtual_ports()
            self._target_mode_status.configure(
                text="Doorlock dispatcher is not implemented yet. Real serial ports are shown."
            )
            Logger.write(
                LogLevel.WARNING,
                "[PROVISION] Doorlock dispatcher is not implemented yet.",
            )
            return

        if target_mode == self.TARGET_THERMOSTAT:
            self.clear_provision_dispatcher()
            self._serial_widget.clear_virtual_ports()
            self._target_mode_status.configure(
                text="Thermostat dispatcher is not implemented yet. Real serial ports are shown."
            )
            Logger.write(
                LogLevel.WARNING,
                "[PROVISION] Thermostat dispatcher is not implemented yet.",
            )
            return

        self.clear_provision_dispatcher()
        self._serial_widget.clear_virtual_ports()
        self._target_mode_status.configure(text="Unknown target mode.")
        Logger.write(
            LogLevel.WARNING,
            f"[PROVISION] Unknown target mode: {target_mode}",
        )

    def _on_provision_manager_event(self, event: ProvisionManagerEvent) -> None:
        """
        Bridge worker-thread manager events into the Tk main thread.
        """
        self.after(0, lambda: self._apply_provision_manager_event(event))

    def _apply_provision_manager_event(self, event: ProvisionManagerEvent) -> None:
        """
        Apply a manager event to the provisioning control widget.
        """
        self._provisioning_control_widget.apply_manager_event(event)
        Logger.write(
            LogLevel.PROGRESS,
            (
                f"[PROVISION] state={event.ui_state.value}, "
                f"dispatcher_ready={event.dispatcher_ready}, "
                f"message={event.message}"
            ),
        )

    def _on_provisioning_user_event(self, event) -> None:
        """
        Handle user actions emitted by the provisioning control widget.
        """
        if event.name == "start_button_clicked":
            self._provision_manager.start()
            return

        if event.name == "finish_button_clicked":
            self._provision_manager.finish()
            return

        Logger.write(
            LogLevel.WARNING,
            f"Unhandled provisioning user event: {event.name}",
        )

    def _on_serial_event(self, event_name: str) -> None:
        """
        Handle serial widget events.

        Provision UI state is no longer derived directly from raw serial
        connection state. Dispatcher readiness is the source of truth.
        """
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

    def set_qr_code_url(self, url: str) -> None:
        self._qr_code_url = str(url).strip()

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
        except Exception as e:
            Logger.write(
                LogLevel.WARNING,
                f"Failed to open QR code URL ({type(e).__name__}: {e})",
            )

    def _on_save_log(self) -> None:
        suggested_name = (
            f"factory_provision_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
        )
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
            Logger.write(
                LogLevel.ERROR,
                f"Log save failed ({type(e).__name__}: {e})",
            )

    def _on_left_panel_resize(self, event) -> None:
        panel_width = max(int(event.width), 1)
        cell_size = max(120, min((panel_width - self._card_gap) // 2, 220))
        self._left_2x2_panel.grid_columnconfigure(0, minsize=cell_size)
        self._left_2x2_panel.grid_columnconfigure(1, minsize=cell_size)
        self._left_2x2_panel.grid_rowconfigure(0, minsize=cell_size)
        self._left_2x2_panel.grid_rowconfigure(1, minsize=cell_size)