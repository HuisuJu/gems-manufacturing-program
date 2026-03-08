import customtkinter as ctk

class SettinPage(ctk.CTkFrame):
    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)
        self.label = ctk.CTkLabel(self, text='Configuration & Paths (Placeholder)')
        self.label.pack(pady=20)
