from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Optional

import customtkinter as ctk

from logger import Logger, LogLevel
from system import MODEL_NAME_KEY, Settings
from view.common.navigation.step import NavigationStep, ReadyCallback
from view.widget.cd_cert_resolver import CDCertResolverWidget
from view.widget.dac_pool_resolver import DacPoolResolverWidget
from view.widget.pai_cert_resolver import PAICertResolverWidget


_TITLE_BOTTOM_SPACING = 18
_SUBTITLE_BOTTOM_SPACING = 20
_CARD_BOTTOM_SPACING = 14
_EXAMPLE_CHECKBOX_BOTTOM_SPACING = 18

_USE_EXAMPLE_SETTING_KEY = "matter_credentials_use_example"


class MatterCredentialsStep(NavigationStep):
    """Step for configuring Matter credentials (DAC / PAI / CD)."""

    def __init__(
        self,
        parent: ctk.CTkFrame,
        on_ready: Optional[ReadyCallback] = None,
        **kwargs,
    ) -> None:
        super().__init__(parent, on_ready=on_ready, **kwargs)

        self.grid_columnconfigure(0, weight=1)

        self._use_example_var = ctk.BooleanVar(
            value=bool(Settings.get(_USE_EXAMPLE_SETTING_KEY) or False)
        )

        self._build_ui()

        if self._use_example_var.get():
            self._apply_example_paths()

        self._update_ready_state()

    def _build_ui(self) -> None:
        """Build step UI."""
        self._title_label = ctk.CTkLabel(
            self,
            text="Matter Credentials",
            anchor="w",
            font=ctk.CTkFont(size=35, weight="bold"),
        )
        self._title_label.grid(
            row=0,
            column=0,
            sticky="ew",
            pady=(0, _TITLE_BOTTOM_SPACING),
        )

        self._subtitle_label = ctk.CTkLabel(
            self,
            text="Configure Matter attestation credentials used for provisioning.",
            anchor="w",
            justify="left",
            font=ctk.CTkFont(size=14),
            text_color=("gray45", "gray65"),
        )
        self._subtitle_label.grid(
            row=1,
            column=0,
            sticky="ew",
            pady=(0, 10),
        )

        self._use_example_checkbox = ctk.CTkCheckBox(
            self,
            text="Use Example",
            variable=self._use_example_var,
            command=self._on_use_example_changed,
        )
        self._use_example_checkbox.grid(
            row=2,
            column=0,
            sticky="w",
            pady=(0, _EXAMPLE_CHECKBOX_BOTTOM_SPACING),
        )

        self._dac_widget = DacPoolResolverWidget(
            self,
            on_changed=self._update_ready_state,
        )
        self._dac_widget.grid(
            row=3,
            column=0,
            sticky="ew",
            pady=(0, _CARD_BOTTOM_SPACING),
        )

        self._pai_widget = PAICertResolverWidget(
            self,
            on_changed=self._update_ready_state,
        )
        self._pai_widget.grid(
            row=4,
            column=0,
            sticky="ew",
            pady=(0, _CARD_BOTTOM_SPACING),
        )

        self._cd_widget = CDCertResolverWidget(
            self,
            on_changed=self._update_ready_state,
        )
        self._cd_widget.grid(
            row=5,
            column=0,
            sticky="ew",
        )

    def _on_use_example_changed(self) -> None:
        """Handle Use Example checkbox changes."""
        use_example = self._use_example_var.get()
        Settings.set(_USE_EXAMPLE_SETTING_KEY, use_example)

        if use_example:
            self._apply_example_paths()

        self._update_ready_state()

    def _apply_example_paths(self) -> None:
        """Apply example paths to all resolver widgets."""
        try:
            model_example_dir = self._get_model_example_dir()

            dac_dir = model_example_dir / "dac"
            pai_path = model_example_dir / "pai.pem"
            cd_path = model_example_dir / "cd.der"

            if not dac_dir.exists() or not dac_dir.is_dir():
                raise FileNotFoundError(
                    f"Example DAC directory was not found: '{dac_dir}'"
                )

            if not pai_path.exists() or not pai_path.is_file():
                raise FileNotFoundError(
                    f"Example PAI file was not found: '{pai_path}'"
                )

            if not cd_path.exists() or not cd_path.is_file():
                raise FileNotFoundError(
                    f"Example CD file was not found: '{cd_path}'"
                )

            self._dac_widget.load_path(dac_dir)
            self._pai_widget.load_path(pai_path)
            self._cd_widget.load_path(cd_path)

            Logger.write(
                LogLevel.DEBUG,
                f"Applied example Matter credentials from '{model_example_dir}'.",
            )

        except Exception as exc:
            Logger.write(
                LogLevel.ALERT,
                f"Failed to apply example Matter credentials: {exc}",
            )

    def _get_model_example_dir(self) -> Path:
        """Return <repo-root>/examples/<model_name> directory."""
        repo_root = self._find_repo_root()
        model_dir_name = self._get_model_dir_name()
        return repo_root / "examples" / model_dir_name

    def _find_repo_root(self) -> Path:
        """
        Find repository root by walking upward until a directory containing
        both 'pc' and 'examples' is found.
        """
        current = Path(__file__).resolve()

        for candidate in [current.parent, *current.parents]:
            if (candidate / "pc").is_dir() and (candidate / "examples").is_dir():
                return candidate

        raise FileNotFoundError(
            "Could not find repository root containing both 'pc' and 'examples'."
        )

    def _get_model_dir_name(self) -> str:
        """Return normalized model directory name."""
        model = Settings.get(MODEL_NAME_KEY)
        if model is None:
            raise ValueError("MODEL_NAME_KEY is not configured.")

        if isinstance(model, Enum):
            model_value = model.value
        else:
            model_value = model

        return str(model_value).strip().lower()

    def _update_ready_state(self) -> None:
        """Update step ready state."""
        self.is_ready = (
            self._dac_widget.is_ready
            and self._pai_widget.is_ready
            and self._cd_widget.is_ready
        )

    def commit(self) -> bool:
        """Commit step state."""
        self._update_ready_state()
        return self.is_ready
