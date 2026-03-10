from __future__ import annotations

from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk

from .view.attestation_path_resolver import (
    AttestationPathResolverConfigurationError,
    CdPathResolver,
    DacCredentialPoolPathResolver,
    PaiCertPathResolver,
)
from settings import SettingsItem, settings as app_settings


class SettingFrame(ctk.CTkFrame):
    """
    Settings page for attestation-related file and directory configuration.

    This frame allows the user to configure:
        - DAC credential pool directory
        - PAI certificate file
        - Certification Declaration file

    The frame uses attestation path resolvers to reflect the currently
    configured paths and to validate whether each path is available.
    """

    def __init__(self, master, **kwargs) -> None:
        super().__init__(master, **kwargs)

        self._dac_pool_resolver = DacCredentialPoolPathResolver()
        self._pai_path_resolver = PaiCertPathResolver()
        self._cd_path_resolver = CdPathResolver()

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=0)
        self.grid_rowconfigure(1, weight=1)

        self._title_label = ctk.CTkLabel(
            self,
            text="Attestation Settings",
            anchor="w",
            font=ctk.CTkFont(size=20, weight="bold"),
        )
        self._title_label.grid(
            row=0,
            column=0,
            padx=20,
            pady=(20, 10),
            sticky="ew",
        )

        self._content_frame = ctk.CTkFrame(self)
        self._content_frame.grid(
            row=1,
            column=0,
            padx=20,
            pady=(0, 20),
            sticky="nsew",
        )
        self._content_frame.grid_columnconfigure(1, weight=1)

        self._build_path_row(
            row=0,
            title="DAC Pool Directory",
            browse_command=self._browse_dac_pool_directory,
            clear_command=self._clear_dac_pool_directory,
        )
        self._dac_pool_value_label = self._row_value_labels["dac_pool"]

        self._build_path_row(
            row=1,
            title="PAI Certificate File",
            browse_command=self._browse_pai_file,
            clear_command=self._clear_pai_file,
        )
        self._pai_file_value_label = self._row_value_labels["pai_file"]

        self._build_path_row(
            row=2,
            title="Certification Declaration File",
            browse_command=self._browse_cd_file,
            clear_command=self._clear_cd_file,
        )
        self._cd_file_value_label = self._row_value_labels["cd_file"]

        self._status_label = ctk.CTkLabel(
            self._content_frame,
            text="",
            anchor="w",
            justify="left",
        )
        self._status_label.grid(
            row=3,
            column=0,
            columnspan=3,
            padx=20,
            pady=(14, 20),
            sticky="ew",
        )

        app_settings.subscribe(
            SettingsItem.DAC_POOL_DIR_PATH,
            self._on_setting_changed,
        )
        app_settings.subscribe(
            SettingsItem.PAI_FILE_PATH,
            self._on_setting_changed,
        )
        app_settings.subscribe(
            SettingsItem.CD_FILE_PATH,
            self._on_setting_changed,
        )

        self._refresh_view()

    def destroy(self) -> None:
        app_settings.unsubscribe(
            SettingsItem.DAC_POOL_DIR_PATH,
            self._on_setting_changed,
        )
        app_settings.unsubscribe(
            SettingsItem.PAI_FILE_PATH,
            self._on_setting_changed,
        )
        app_settings.unsubscribe(
            SettingsItem.CD_FILE_PATH,
            self._on_setting_changed,
        )
        super().destroy()

    def _build_path_row(
        self,
        row: int,
        title: str,
        browse_command,
        clear_command,
    ) -> None:
        if not hasattr(self, "_row_value_labels"):
            self._row_value_labels: dict[str, ctk.CTkLabel] = {}

        key = {
            0: "dac_pool",
            1: "pai_file",
            2: "cd_file",
        }[row]

        title_label = ctk.CTkLabel(
            self._content_frame,
            text=title,
            anchor="w",
        )
        title_label.grid(
            row=row,
            column=0,
            padx=(20, 10),
            pady=10,
            sticky="w",
        )

        value_label = ctk.CTkLabel(
            self._content_frame,
            text="",
            anchor="w",
            justify="left",
            wraplength=520,
        )
        value_label.grid(
            row=row,
            column=1,
            padx=(0, 10),
            pady=10,
            sticky="ew",
        )

        button_frame = ctk.CTkFrame(self._content_frame, fg_color="transparent")
        button_frame.grid(
            row=row,
            column=2,
            padx=(0, 20),
            pady=10,
            sticky="e",
        )

        browse_button = ctk.CTkButton(
            button_frame,
            text="Browse",
            width=90,
            command=browse_command,
        )
        browse_button.grid(row=0, column=0, padx=(0, 6), pady=0)

        clear_button = ctk.CTkButton(
            button_frame,
            text="Clear",
            width=80,
            command=clear_command,
        )
        clear_button.grid(row=0, column=1, padx=0, pady=0)

        self._row_value_labels[key] = value_label

    def _on_setting_changed(self, item: SettingsItem, value: object | None) -> None:
        """
        Refresh the UI when one of the attestation-related settings changes.
        """
        if item not in (
            SettingsItem.DAC_POOL_DIR_PATH,
            SettingsItem.PAI_FILE_PATH,
            SettingsItem.CD_FILE_PATH,
        ):
            return

        self.after(0, self._refresh_view)

    def _refresh_view(self) -> None:
        """
        Refresh all path widgets and summary status.
        """
        self._refresh_dac_pool_widget()
        self._refresh_pai_file_widget()
        self._refresh_cd_file_widget()
        self._refresh_status_label()

    def _refresh_dac_pool_widget(self) -> None:
        """
        Refresh the DAC pool directory row from the resolver state.
        """
        directory = self._dac_pool_resolver.directory
        display_text = "" if directory is None else str(directory)
        self._dac_pool_value_label.configure(text=display_text)

    def _refresh_pai_file_widget(self) -> None:
        """
        Refresh the PAI certificate file row from the resolver state.
        """
        try:
            path = self._pai_path_resolver.get_path()
            display_text = str(path)
        except AttestationPathResolverConfigurationError:
            display_text = ""

        self._pai_file_value_label.configure(text=display_text)

    def _refresh_cd_file_widget(self) -> None:
        """
        Refresh the Certification Declaration file row from the resolver state.
        """
        try:
            path = self._cd_path_resolver.get_path()
            display_text = str(path)
        except AttestationPathResolverConfigurationError:
            display_text = ""

        self._cd_file_value_label.configure(text=display_text)

    def _refresh_status_label(self) -> None:
        """
        Refresh the summary text shown below the path rows.
        """
        lines: list[str] = []

        try:
            report = self._dac_pool_resolver.get_inventory_report()
            lines.append(
                "DAC Pool: "
                f"total={report.total}, "
                f"ready={report.ready}, "
                f"consumed={report.consumed}, "
                f"error={report.error}"
            )
        except Exception as exc:
            lines.append(f"DAC Pool: {exc}")

        try:
            pai_path = self._pai_path_resolver.get_path()
            lines.append(f"PAI: {pai_path}")
        except Exception as exc:
            lines.append(f"PAI: {exc}")

        try:
            cd_path = self._cd_path_resolver.get_path()
            lines.append(f"CD: {cd_path}")
        except Exception as exc:
            lines.append(f"CD: {exc}")

        self._status_label.configure(text="\n".join(lines))

    def _browse_dac_pool_directory(self) -> None:
        """
        Open a directory dialog and apply the selected DAC pool directory.
        """
        selected_path = filedialog.askdirectory(
            title="Select DAC Pool Directory",
            parent=self,
        )
        if not selected_path:
            return

        try:
            app_settings.set(
                SettingsItem.DAC_POOL_DIR_PATH,
                self._normalize_selected_path(selected_path),
            )
        except Exception as exc:
            messagebox.showerror(
                "DAC Pool Directory",
                str(exc),
                parent=self,
            )

    def _browse_pai_file(self) -> None:
        """
        Open a file dialog and apply the selected PAI certificate file.
        """
        selected_path = filedialog.askopenfilename(
            title="Select PAI Certificate File",
            filetypes=[("PEM files", "*.pem"), ("All files", "*.*")],
            parent=self,
        )
        if not selected_path:
            return

        try:
            app_settings.set(
                SettingsItem.PAI_FILE_PATH,
                self._normalize_selected_path(selected_path),
            )
        except Exception as exc:
            messagebox.showerror(
                "PAI Certificate File",
                str(exc),
                parent=self,
            )

    def _browse_cd_file(self) -> None:
        """
        Open a file dialog and apply the selected Certification Declaration file.
        """
        selected_path = filedialog.askopenfilename(
            title="Select Certification Declaration File",
            filetypes=[("DER files", "*.der"), ("All files", "*.*")],
            parent=self,
        )
        if not selected_path:
            return

        try:
            app_settings.set(
                SettingsItem.CD_FILE_PATH,
                self._normalize_selected_path(selected_path),
            )
        except Exception as exc:
            messagebox.showerror(
                "Certification Declaration File",
                str(exc),
                parent=self,
            )

    def _clear_dac_pool_directory(self) -> None:
        """
        Clear the DAC pool directory setting.
        """
        try:
            app_settings.clear(SettingsItem.DAC_POOL_DIR_PATH)
        except Exception as exc:
            messagebox.showerror(
                "DAC Pool Directory",
                str(exc),
                parent=self,
            )

    def _clear_pai_file(self) -> None:
        """
        Clear the PAI certificate file setting.
        """
        try:
            app_settings.clear(SettingsItem.PAI_FILE_PATH)
        except Exception as exc:
            messagebox.showerror(
                "PAI Certificate File",
                str(exc),
                parent=self,
            )

    def _clear_cd_file(self) -> None:
        """
        Clear the Certification Declaration file setting.
        """
        try:
            app_settings.clear(SettingsItem.CD_FILE_PATH)
        except Exception as exc:
            messagebox.showerror(
                "Certification Declaration File",
                str(exc),
                parent=self,
            )

    @staticmethod
    def _normalize_selected_path(selected_path: str | None) -> Path | None:
        """
        Normalize a selected path string into a Path instance.

        Empty selections are converted to None.
        """
        if selected_path is None:
            return None

        normalized = selected_path.strip()
        if not normalized:
            return None

        return Path(normalized).expanduser().resolve()