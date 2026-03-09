import customtkinter as ctk

from .widget.path_finder_widget import PathFinderWidget


class SettingFrame(ctk.CTkFrame):
    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=0)

        self._path_finder_widget = PathFinderWidget(self)
        self._path_finder_widget.grid(
            row=0,
            column=0,
            padx=20,
            pady=20,
            sticky="nsew",
        )