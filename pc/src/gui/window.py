import customtkinter as ctk

from .startup_dialog import StartupSelectionDialog


class Window(ctk.CTk):
    """
    Main application window.

    Startup flow:
        1. Create hidden root window.
        2. Show startup selection dialog.
        3. If confirmed, initialize tabs/pages.
        4. Apply startup selection to pages.
        5. Show main window.
    """

    def __init__(self, page_list: list[tuple[type[ctk.CTkFrame], str]]):
        super().__init__()

        self.title("Hyundai HT GEMS Factory Provisioning Tool")
        self.selected_models: list[str] = []
        self.selected_model: str = ""
        self.pages: dict[str, ctk.CTkFrame] = {}

        self.withdraw()

        selected_mode = self._show_startup_selection_dialog()
        if not selected_mode:
            return

        self.selected_models = [selected_mode]
        self.selected_model = selected_mode

        self._initialize_main_layout(page_list)
        self._apply_startup_selection_to_pages()

        self.deiconify()

    def _show_startup_selection_dialog(self) -> str:
        """
        Show the startup selection dialog before building the main UI.
        """
        dialog = StartupSelectionDialog(self)
        return dialog.show_modal()

    def _initialize_main_layout(
        self,
        page_list: list[tuple[type[ctk.CTkFrame], str]],
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

        for page_frame, page_name in page_list:
            tab = self._tabview.add(page_name)
            tab.grid_rowconfigure(0, weight=1)
            tab.grid_columnconfigure(0, weight=1)

            page = page_frame(tab)
            page.grid(row=0, column=0, sticky="nsew")
            self.pages[page_name] = page

    def _apply_startup_selection_to_pages(self) -> None:
        """
        Apply the startup model selection to page instances.
        """
        provisioning_page = self.pages.get("Provisioning")
        if provisioning_page is not None:
            selected = self.selected_model.strip().lower()
            try:
                if hasattr(provisioning_page, "set_target_mode"):
                    provisioning_page.set_target_mode(selected)
            except Exception:
                pass