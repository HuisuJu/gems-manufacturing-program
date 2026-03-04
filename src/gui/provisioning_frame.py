import customtkinter as ctk
from gui.serial_widget import SerialWidget

class ProvisioningFrame(ctk.CTkFrame):
    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)
        
        self.serial_widget = SerialWidget(self)
        self.serial_widget.grid(row=0, column=0, padx=20, 
                                pady=(0, 10), sticky='nsew')