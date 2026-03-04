import customtkinter as ctk
from gui.serial_widget import SerialWidget
from gui.log_widget import LogWidget


class ProvisioningFrame(ctk.CTkFrame):
    NUM_COLUMNS = 3
    NUM_ROWS    = 3

    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)

        for c in range(self.NUM_COLUMNS):
            self.grid_columnconfigure(c, weight=1, uniform='toprow')

        for r in range(self.NUM_ROWS - 1):
            self.grid_rowconfigure(r, weight=0)
        self.grid_rowconfigure(r, weight=1)

        self.serial_widget = SerialWidget(self)
        self.serial_widget.grid(
            row=0,
            column=0,
            padx=20,
            pady=(0,10),
            sticky="nsew"
        )

        self.log_widget = LogWidget(self)
        self.log_widget.grid(
            row=self.NUM_ROWS-1,
            column=0,
            columnspan=self.NUM_COLUMNS,
            padx=20,
            pady=(0,20),
            sticky="nsew"
        )
