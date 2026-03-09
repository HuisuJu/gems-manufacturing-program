import customtkinter as ctk


class Window(ctk.CTk):
    def __init__(self, page_list: list[tuple[type[ctk.CTkFrame], str]]):
        super().__init__()

        self.title('Hyundai HT GEMS Factory Provisioning Tool')
        self.selected_models: list[str] = []

        self.withdraw()
        self._show_startup_setting_dialog()

        if not self.winfo_exists():
            return

        self.deiconify()
        self.wm_attributes('-zoomed', True)
        
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self._tabview = ctk.CTkTabview(self)
        self._tabview.grid(row=0, column=0, padx=20, pady=(0, 20), sticky='nsew')

        for page_frame, page_name in page_list:
            tab = self._tabview.add(page_name)
            tab.grid_rowconfigure(0, weight=1)
            tab.grid_columnconfigure(0, weight=1)

            page = page_frame(tab)
            page.grid(row=0, column=0, sticky='nsew')

    def _show_startup_setting_dialog(self) -> None:
        dialog = ctk.CTkToplevel(self)
        dialog.withdraw()
        dialog.title('Startup Settings')
        dialog.resizable(False, False)
        dialog.grab_set()

        dialog.grid_columnconfigure(0, weight=1)

        title_label = ctk.CTkLabel(
            dialog,
            text='Select Model',
            font=ctk.CTkFont(size=16, weight='bold'),
        )
        title_label.grid(row=0, column=0, padx=20, pady=(20, 8), sticky='w')

        subtitle_label = ctk.CTkLabel(
            dialog,
            text='Choose at least one model to continue.',
            font=ctk.CTkFont(size=12),
            text_color='gray70',
        )
        subtitle_label.grid(row=1, column=0, padx=20, pady=(0, 10), sticky='w')

        model_var = ctk.StringVar(value='')

        options_frame = ctk.CTkFrame(dialog, fg_color='transparent')
        options_frame.grid(row=2, column=0, padx=20, pady=(0, 10), sticky='ew')
        options_frame.grid_columnconfigure(0, weight=1)

        doorlock_radio = ctk.CTkRadioButton(
            options_frame,
            text='Doorlock',
            variable=model_var,
            value='Doorlock',
        )
        doorlock_radio.grid(row=0, column=0, padx=0, pady=(0, 8), sticky='w')

        thermostat_radio = ctk.CTkRadioButton(
            options_frame,
            text='Thermostat',
            variable=model_var,
            value='Thermostat',
        )
        thermostat_radio.grid(row=1, column=0, padx=0, pady=(0, 0), sticky='w')

        status_label = ctk.CTkLabel(
            dialog,
            text='',
            font=ctk.CTkFont(size=11),
            text_color='red',
        )
        status_label.grid(row=3, column=0, padx=20, pady=(0, 6), sticky='w')

        button_frame = ctk.CTkFrame(dialog, fg_color='transparent')
        button_frame.grid(row=4, column=0, padx=20, pady=(0, 18), sticky='e')

        def update_ok_state() -> None:
            selected_model = model_var.get()
            ok_button.configure(state='normal' if selected_model else 'disabled')
            if selected_model:
                status_label.configure(text='')

        def on_ok() -> None:
            selected_model = model_var.get()

            if not selected_model:
                status_label.configure(text='Select one model.')
                return

            self.selected_models = [selected_model]
            dialog.grab_release()
            dialog.destroy()

        ok_button = ctk.CTkButton(
            button_frame,
            text='OK',
            command=on_ok,
            state='disabled',
        )
        ok_button.grid(row=0, column=0, padx=0, pady=0)

        model_var.trace_add('write', lambda *_: update_ok_state())

        def on_close() -> None:
            dialog.grab_release()
            self.destroy()

        def unset_topmost() -> None:
            if dialog.winfo_exists():
                dialog.attributes('-topmost', False)

        dialog.update_idletasks()
        width = dialog.winfo_reqwidth()
        height = dialog.winfo_reqheight()
        screen_width = dialog.winfo_screenwidth()
        screen_height = dialog.winfo_screenheight()
        x = (screen_width - width) // 2
        y = (screen_height - height) // 2
        dialog.geometry(f'{width}x{height}+{x}+{y}')
        dialog.deiconify()
        dialog.lift()
        dialog.attributes('-topmost', True)

        dialog.protocol('WM_DELETE_WINDOW', on_close)
        dialog.focus_force()
        dialog.after(50, unset_topmost)
        dialog.wait_window()
