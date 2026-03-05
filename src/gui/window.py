import customtkinter as ctk


class Window(ctk.CTk):
    def __init__(self, page_list: list[tuple[type[ctk.CTkFrame], str]]):
        super().__init__()

        self.title("Hyundai HT GEMS Factory Provisioning Tool")
        self.wm_attributes("-zoomed", True)

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