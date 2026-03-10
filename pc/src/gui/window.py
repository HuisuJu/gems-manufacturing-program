from __future__ import annotations

from typing import Callable

import customtkinter as ctk

from settings import ModelName
from .startup_dialog import StartupSelectionDialog


PageFactory = Callable[[ctk.CTkFrame], ctk.CTkFrame]


class Window(ctk.CTk):
    """
    Main application window.

    Startup flow:
        1. Create hidden root window.
        2. Show startup selection dialog.
        3. If confirmed, initialize tabs/pages.
        4. Show main window.

    Notes:
        - The startup dialog is responsible for storing MODEL_NAME into the
          global settings module.
        - Page instances are exposed through self.pages.
    """

    def __init__(self, page_factories: list[tuple[PageFactory, str]]):
        super().__init__()

        self.title("Hyundai HT GEMS Factory Provisioning Tool")
        self.selected_model_name: ModelName | None = None
        self.pages: dict[str, ctk.CTkFrame] = {}

        self.withdraw()

        selected_model_name = self._show_startup_selection_dialog()
        if selected_model_name is None:
            return

        self.selected_model_name = selected_model_name

        self._initialize_main_layout(page_factories)
        self.deiconify()

    def _show_startup_selection_dialog(self) -> ModelName | None:
        """
        Show the startup selection dialog before building the main UI.
        """
        dialog = StartupSelectionDialog(self)
        return dialog.show_modal()

    def _initialize_main_layout(
        self,
        page_factories: list[tuple[PageFactory, str]],
    ) -> None:
        """
        Build the main window layout and page tabs.
        """
        try:
            self.wm_attributes("-zoomed", True)
        except Exception:
            try:
                self.attributes("-zoomed", True)
            except Exception:
                pass

        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self._tabview = ctk.CTkTabview(self)
        self._tabview.grid(row=0, column=0, padx=20, pady=(0, 20), sticky="nsew")

        for page_factory, page_name in page_factories:
            tab = self._tabview.add(page_name)
            tab.grid_rowconfigure(0, weight=1)
            tab.grid_columnconfigure(0, weight=1)

            page = page_factory(tab)
            page.grid(row=0, column=0, sticky="nsew")
            self.pages[page_name] = page