import customtkinter as ctk

from factory_data import FactoryDataPoolManager
from .factory_data_widget import FactoryDataPoolWidget


class SettingPage(ctk.CTkFrame):

    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=0)

        self._pool_manager = FactoryDataPoolManager()

        self._factory_data_widget = FactoryDataPoolWidget(self)
        self._factory_data_widget.grid(
            row=0,
            column=0,
            padx=20,
            pady=20,
            sticky="nsew",
        )

        self._factory_data_widget.set_path_listener(
            self._on_factory_data_path_selected
        )

        current = self._pool_manager.get_pool_path()
        if current is not None:
            self._factory_data_widget.set_path(current)

    def _on_factory_data_path_selected(self, path: str) -> None:
        """
        Apply selected factory data pool path.
        """
        try:
            self._pool_manager.set_pool_path(path)
        except Exception:
            pass


# Backward compatibility
SettinPage = SettingPage