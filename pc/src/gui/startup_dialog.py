import customtkinter as ctk


class StartupSelectionDialog(ctk.CTkToplevel):
    """
    Modal dialog shown before the main application pages are initialized.

    The dialog asks the user to choose one target mode:
        - doorlock
        - thermostat
        - emulator
    """

    MODE_DOORLOCK = "doorlock"
    MODE_THERMOSTAT = "thermostat"
    MODE_EMULATOR = "emulator"

    def __init__(self, master: ctk.CTk):
        super().__init__(master)

        self.withdraw()
        self.title("Startup Settings")
        self.resizable(False, False)
        self.grab_set()

        self.selected_mode: str = ""
        self.was_confirmed: bool = False

        self.grid_columnconfigure(0, weight=1)

        self._mode_var = ctk.StringVar(value="")

        title_label = ctk.CTkLabel(
            self,
            text="Select Model",
            font=ctk.CTkFont(size=16, weight="bold"),
        )
        title_label.grid(row=0, column=0, padx=20, pady=(20, 8), sticky="w")

        subtitle_label = ctk.CTkLabel(
            self,
            text="Choose one target mode to continue.",
            font=ctk.CTkFont(size=12),
            text_color="gray70",
        )
        subtitle_label.grid(row=1, column=0, padx=20, pady=(0, 10), sticky="w")

        options_frame = ctk.CTkFrame(self, fg_color="transparent")
        options_frame.grid(row=2, column=0, padx=20, pady=(0, 10), sticky="ew")
        options_frame.grid_columnconfigure(0, weight=1)

        self._doorlock_radio = ctk.CTkRadioButton(
            options_frame,
            text="Doorlock",
            variable=self._mode_var,
            value=self.MODE_DOORLOCK,
        )
        self._doorlock_radio.grid(row=0, column=0, padx=0, pady=(0, 8), sticky="w")

        self._thermostat_radio = ctk.CTkRadioButton(
            options_frame,
            text="Thermostat",
            variable=self._mode_var,
            value=self.MODE_THERMOSTAT,
        )
        self._thermostat_radio.grid(row=1, column=0, padx=0, pady=(0, 8), sticky="w")

        self._emulator_radio = ctk.CTkRadioButton(
            options_frame,
            text="Emulator",
            variable=self._mode_var,
            value=self.MODE_EMULATOR,
        )
        self._emulator_radio.grid(row=2, column=0, padx=0, pady=(0, 0), sticky="w")

        self._status_label = ctk.CTkLabel(
            self,
            text="",
            font=ctk.CTkFont(size=11),
            text_color="red",
        )
        self._status_label.grid(row=3, column=0, padx=20, pady=(0, 6), sticky="w")

        button_frame = ctk.CTkFrame(self, fg_color="transparent")
        button_frame.grid(row=4, column=0, padx=20, pady=(0, 18), sticky="e")

        self._ok_button = ctk.CTkButton(
            button_frame,
            text="OK",
            command=self._on_ok,
            state="disabled",
        )
        self._ok_button.grid(row=0, column=0, padx=0, pady=0)

        self._mode_var.trace_add("write", lambda *_: self._update_ok_state())
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self._show_centered()

    def show_modal(self) -> str:
        """
        Show the dialog modally and return the selected mode.
        """
        self.wait_window()
        return self.selected_mode if self.was_confirmed else ""

    def _update_ok_state(self) -> None:
        selected_mode = self._mode_var.get()
        self._ok_button.configure(state="normal" if selected_mode else "disabled")
        if selected_mode:
            self._status_label.configure(text="")

    def _on_ok(self) -> None:
        selected_mode = self._mode_var.get()

        if not selected_mode:
            self._status_label.configure(text="Select one mode.")
            return

        self.selected_mode = selected_mode
        self.was_confirmed = True
        self.grab_release()
        self.destroy()

    def _on_close(self) -> None:
        self.was_confirmed = False
        self.selected_mode = ""
        self.grab_release()
        self.destroy()
        if self.master is not None and self.master.winfo_exists():
            self.master.destroy()

    def _show_centered(self) -> None:
        def unset_topmost() -> None:
            if self.winfo_exists():
                self.attributes("-topmost", False)

        self.update_idletasks()
        width = self.winfo_reqwidth()
        height = self.winfo_reqheight()
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        x = (screen_width - width) // 2
        y = (screen_height - height) // 2

        self.geometry(f"{width}x{height}+{x}+{y}")
        self.deiconify()
        self.lift()
        self.attributes("-topmost", True)
        self.focus_force()
        self.after(50, unset_topmost)