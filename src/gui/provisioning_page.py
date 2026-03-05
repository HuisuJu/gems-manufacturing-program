import customtkinter as ctk

from connection import SerialManager
from session import Session

from gui.serial_widget import SerialWidget
from gui.log_widget import LogWidget


class ProvisioningPage(ctk.CTkFrame):
    NUM_COLUMNS = 3
    NUM_ROWS = 3

    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)

        for c in range(self.NUM_COLUMNS):
            self.grid_columnconfigure(c, weight=1, uniform="toprow")

        for r in range(self.NUM_ROWS):
            self.grid_rowconfigure(r, weight=0)
        self.grid_rowconfigure(self.NUM_ROWS - 1, weight=1)

        self._serial_manager = SerialManager(Session.on_serial_frame)
        Session.bind_serial(self._serial_manager)

        self._serial_widget = SerialWidget(self, self._serial_manager)
        self._serial_widget.grid(
            row=0,
            column=0,
            padx=20,
            pady=(0, 10),
            sticky="nsew",
        )

        self._log_widget = LogWidget(self)
        self._log_widget.grid(
            row=self.NUM_ROWS - 1,
            column=0,
            columnspan=self.NUM_COLUMNS,
            padx=20,
            pady=(0, 20),
            sticky="nsew",
        )