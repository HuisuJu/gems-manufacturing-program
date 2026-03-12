from __future__ import annotations

import tkinter as tk

import customtkinter as ctk

from logger import Logger, LogLevel

from system import ModelName, Settings, SettingsItem


class StartupSelectionDialog(ctk.CTkToplevel):
    """
    Modal dialog shown before the main application pages are initialized.

    The dialog asks the user to choose one target model:
        - doorlock
        - thermostat
        - emulator
    """

    def __init__(self, master: ctk.CTk):
        super().__init__(master)

        self.withdraw()
        self.title("Startup Settings")
        self.resizable(False, False)
        try:
            self.grab_set()
        except tk.TclError as exc:
            Logger.write(
                LogLevel.ALERT,
                "시작 다이얼로그 모달 잠금(grab_set) 적용에 실패했습니다. "
                "일부 환경에서 포커스 동작이 다를 수 있습니다. "
                f"({type(exc).__name__}: {exc})",
            )

        self.selected_model_name: ModelName | None = None
        self.was_confirmed: bool = False

        self.grid_columnconfigure(0, weight=1)

        self._model_var = ctk.StringVar(value="")

        title_label = ctk.CTkLabel(
            self,
            text="Select Model",
            font=ctk.CTkFont(size=16, weight="bold"),
        )
        title_label.grid(row=0, column=0, padx=20, pady=(20, 8), sticky="w")

        subtitle_label = ctk.CTkLabel(
            self,
            text="Choose one target model to continue.",
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
            variable=self._model_var,
            value=ModelName.DOORLOCK.value,
        )
        self._doorlock_radio.grid(row=0, column=0, padx=0, pady=(0, 8), sticky="w")

        self._thermostat_radio = ctk.CTkRadioButton(
            options_frame,
            text="Thermostat",
            variable=self._model_var,
            value=ModelName.THERMOSTAT.value,
        )
        self._thermostat_radio.grid(row=1, column=0, padx=0, pady=(0, 8), sticky="w")

        self._emulator_radio = ctk.CTkRadioButton(
            options_frame,
            text="Emulator",
            variable=self._model_var,
            value=ModelName.EMULATOR.value,
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

        self._model_var.trace_add("write", lambda *_: self._update_ok_state())
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self._show_centered()

    def show_modal(self) -> ModelName | None:
        """
        Show the dialog modally and return the selected model name.

        Returns:
            Selected ModelName when confirmed, otherwise None.
        """
        self.wait_window()
        return self.selected_model_name if self.was_confirmed else None

    def _update_ok_state(self) -> None:
        selected_model = self._model_var.get()
        self._ok_button.configure(state="normal" if selected_model else "disabled")
        if selected_model:
            self._status_label.configure(text="")

    def _on_ok(self) -> None:
        selected_model = self._model_var.get()

        if not selected_model:
            self._status_label.configure(text="Select one model.")
            return

        try:
            model_name = ModelName(selected_model)
            Settings.set(SettingsItem.MODEL_NAME, model_name)
        except Exception as exc:
            self._status_label.configure(text=str(exc))
            return

        self.selected_model_name = model_name
        self.was_confirmed = True
        try:
            self.grab_release()
        except tk.TclError:
            pass
        self.destroy()

    def _on_close(self) -> None:
        self.was_confirmed = False
        self.selected_model_name = None
        try:
            self.grab_release()
        except tk.TclError:
            pass
        self.destroy()

        if self.master is not None and self.master.winfo_exists():
            self.master.destroy()

    def _show_centered(self) -> None:

        def unset_topmost() -> None:
            if self.winfo_exists():
                try:
                    self.attributes("-topmost", False)
                except tk.TclError:
                    pass

        self.update_idletasks()
        width = self.winfo_reqwidth()
        height = self.winfo_reqheight()
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        x = (screen_width - width) // 2
        y = (screen_height - height) // 2

        self.geometry(f"{width}x{height}+{x}+{y}")
        try:
            self.deiconify()
            self.lift()
        except tk.TclError as exc:
            Logger.write(
                LogLevel.ALERT,
                "시작 다이얼로그 표시(deiconify/lift) 중 오류가 발생했습니다. "
                f"({type(exc).__name__}: {exc})",
            )

        try:
            self.attributes("-topmost", True)
        except tk.TclError as exc:
            Logger.write(
                LogLevel.ALERT,
                "시작 다이얼로그 topmost 설정에 실패했습니다. "
                f"({type(exc).__name__}: {exc})",
            )

        try:
            self.focus_force()
        except tk.TclError:
            pass
        self.after(50, unset_topmost)
