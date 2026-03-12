from __future__ import annotations

from pathlib import Path

from tkinter import filedialog, messagebox

import customtkinter as ctk

import storage

from system import Settings, SettingsItem


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

        Settings.subscribe(
            SettingsItem.DAC_POOL_DIR_PATH,
            self._on_setting_changed,
        )
        Settings.subscribe(
            SettingsItem.PAI_FILE_PATH,
            self._on_setting_changed,
        )
        Settings.subscribe(
            SettingsItem.CD_FILE_PATH,
            self._on_setting_changed,
        )

        self._refresh_view()

    def destroy(self) -> None:
        Settings.unsubscribe(
            SettingsItem.DAC_POOL_DIR_PATH,
            self._on_setting_changed,
        )
        Settings.unsubscribe(
            SettingsItem.PAI_FILE_PATH,
            self._on_setting_changed,
        )
        Settings.unsubscribe(
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
        Refresh the DAC pool directory row from settings.
        """
        directory = Settings.get(SettingsItem.DAC_POOL_DIR_PATH)
        display_text = "" if directory is None else str(directory)
        self._dac_pool_value_label.configure(text=display_text)

    def _refresh_pai_file_widget(self) -> None:
        """
        Refresh the PAI certificate file row from settings.
        """
        path = Settings.get(SettingsItem.PAI_FILE_PATH)
        display_text = "" if path is None else str(path)

        self._pai_file_value_label.configure(text=display_text)

    def _refresh_cd_file_widget(self) -> None:
        """
        Refresh the Certification Declaration file row from settings.
        """
        path = Settings.get(SettingsItem.CD_FILE_PATH)
        display_text = "" if path is None else str(path)

        self._cd_file_value_label.configure(text=display_text)

    def _refresh_status_label(self) -> None:
        """
        Refresh the summary text shown below the path rows.
        """
        lines: list[str] = []

        try:
            report = storage.dac_pool_store.get_inventory_report()
            lines.append(
                "DAC Pool: "
                f"total={report.total}, "
                f"ready={report.ready}, "
                f"consumed={report.consumed}, "
                f"error={report.error}"
            )
        except Exception as exc:
            lines.append(f"DAC Pool: {exc}")

        pai_path = Settings.get(SettingsItem.PAI_FILE_PATH)
        if pai_path is None:
            lines.append("PAI: not configured")
        else:
            lines.append(f"PAI: {pai_path}")

        cd_path = Settings.get(SettingsItem.CD_FILE_PATH)
        lines.append("CD: not configured" if cd_path is None else f"CD: {cd_path}")

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
            normalized_path = self._normalize_selected_path(selected_path)
            validated_path = self._validate_dac_pool_directory(normalized_path)
            Settings.set(
                SettingsItem.DAC_POOL_DIR_PATH,
                validated_path,
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
            normalized_path = self._normalize_selected_path(selected_path)
            validated_path = self._validate_pem_or_der_file(
                normalized_path,
                field_label="PAI certificate file",
            )
            storage.pai_cert_store.load(validated_path)
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
            normalized_path = self._normalize_selected_path(selected_path)
            validated_path = self._validate_pem_or_der_file(
                normalized_path,
                field_label="Certification Declaration file",
            )
            storage.cd_cert_store.load(validated_path)
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
            Settings.clear(SettingsItem.DAC_POOL_DIR_PATH)
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
            storage.pai_cert_store.load(None)
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
            storage.cd_cert_store.load(None)
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

    @staticmethod

    def _validate_dac_pool_directory(path: Path | None) -> Path:
        """
        Validate DAC pool directory selection.
        """
        if path is None:
            raise ValueError("DAC pool directory is required.")

        if not path.exists():
            raise ValueError("Selected DAC pool directory does not exist.")

        if not path.is_dir():
            raise ValueError("Selected DAC pool path is not a directory.")

        pem_files = [
            child for child in path.iterdir()
            if child.is_file() and child.suffix.lower() == ".pem"
        ]
        if not pem_files:
            raise ValueError(
                "Selected DAC pool directory does not contain any .pem files."
            )

        return path

    @staticmethod

    def _validate_pem_or_der_file(
        path: Path | None,
        *,
        field_label: str,
    ) -> Path:
        """
        Validate file selection for attestation artifacts.
        """
        if path is None:
            raise ValueError(f"{field_label} is required.")

        if not path.exists():
            raise ValueError(f"Selected {field_label} does not exist.")

        if not path.is_file():
            raise ValueError(f"Selected {field_label} is not a file.")

        if path.suffix.lower() not in {".pem", ".der"}:
            raise ValueError(
                f"Selected {field_label} must be a .pem or .der file."
            )

        return path
