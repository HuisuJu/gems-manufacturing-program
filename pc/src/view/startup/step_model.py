from __future__ import annotations

from typing import Optional

import customtkinter as ctk

from system import MODEL_NAME_KEY, ModelName, Settings
from view.common.navigation.step import NavigationStep


_TITLE_BOTTOM_SPACING = 18
_SUBTITLE_BOTTOM_SPACING = 20
_RADIO_SPACING = 14


class ModelSelectionStep(NavigationStep):
    """Startup step for selecting target model."""

    _MODEL_ITEMS: tuple[tuple[str, ModelName], ...] = (
        ("DoorLock", ModelName.DOORLOCK),
        ("Thermostat", ModelName.THERMOSTAT),
        ("Emulator", ModelName.EMULATOR),
    )

    def __init__(
        self,
        parent: ctk.CTkFrame,
        on_ready=None,
        **kwargs,
    ) -> None:
        super().__init__(parent, on_ready=on_ready, **kwargs)

        self.grid_columnconfigure(0, weight=1)

        previous = Settings.get(MODEL_NAME_KEY)
        self._model_var = ctk.StringVar(value=previous or "")

        self._build_ui()

        self.is_ready = self.selected_model is not None

    def _build_ui(self) -> None:
        """Build step UI."""
        self._title_label = ctk.CTkLabel(
            self,
            text="Select Model",
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
            text="Please select the device model to continue.",
            anchor="w",
            justify="left",
            font=ctk.CTkFont(size=15),
            text_color="gray40",
        )
        self._subtitle_label.grid(
            row=1,
            column=0,
            sticky="ew",
            pady=(0, _SUBTITLE_BOTTOM_SPACING),
        )

        self._radio_buttons: list[ctk.CTkRadioButton] = []

        for row, (label, model) in enumerate(self._MODEL_ITEMS, start=2):
            radio = ctk.CTkRadioButton(
                self,
                text=label,
                variable=self._model_var,
                value=model.value,
                font=ctk.CTkFont(size=16),
                width=260,
                height=36,
                radiobutton_width=18,
                radiobutton_height=18,
                command=self._on_model_changed,
            )
            radio.grid(
                row=row,
                column=0,
                sticky="w",
                pady=(0, _RADIO_SPACING),
                padx=15,
            )
            self._radio_buttons.append(radio)

    @property
    def selected_model(self) -> Optional[ModelName]:
        """Return selected model or None."""
        value = self._model_var.get()
        if not value:
            return None
        return ModelName(value)

    def commit(self) -> bool:
        """Persist selected model."""
        selected_model = self.selected_model
        if selected_model is None:
            return False

        Settings.set(MODEL_NAME_KEY, selected_model.value)
        return True

    def _on_model_changed(self) -> None:
        """Update ready state when model selection changes."""
        self.is_ready = self.selected_model is not None
