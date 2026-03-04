import customtkinter as ctk

class Window(ctk.CTk):
    def __init__(self, page_list: list[tuple[type[ctk.CTkFrame], str]]):
        super().__init__()

        self.title('Hyundai HT GEMS Factory Provisioning Tool')
        self.wm_attributes('-zoomed', True)

        self.tabview = ctk.CTkTabview(self)
        self.tabview.pack(padx=20, pady=(0, 20), fill='both', expand=True)

        for page_frame, page_name in page_list:
            tab = self.tabview.add(page_name)
            page = page_frame(tab)
            page.pack(fill='both', expand=True)
