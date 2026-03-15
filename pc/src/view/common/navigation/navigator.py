from __future__ import annotations

from collections.abc import Callable

import customtkinter as ctk

from .selector import NavigationSelectType, NavigationSelector
from .step import NavigationStep


FinishedCallback = Callable[[], None]


class Navigator(ctk.CTkFrame):
    """Main panel that manages navigation steps and selector buttons."""

    def __init__(
        self,
        parent: ctk.CTkFrame | ctk.CTkToplevel,
        steps: list[type[NavigationStep]],
        on_finished: FinishedCallback | None = None,
        **kwargs,
    ) -> None:
        super().__init__(parent, fg_color="transparent", **kwargs)

        if not steps:
            raise ValueError("Navigator requires at least one navigation step.")

        self._on_finished = on_finished
        self._current_step_index = 0
        self._steps: list[NavigationStep] = []

        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self._step_container = ctk.CTkFrame(self, fg_color="transparent")
        self._step_container.grid(
            row=0,
            column=0,
            padx=40,
            pady=(36, 18),
            sticky="nsew",
        )
        self._step_container.grid_rowconfigure(0, weight=1)
        self._step_container.grid_columnconfigure(0, weight=1)

        self._selector = NavigationSelector(
            self,
            on_clicked=self._on_selector_clicked,
        )
        self._selector.grid(
            row=1,
            column=0,
            padx=40,
            pady=(0, 32),
            sticky="e",
        )

        self._steps = [
            step_class(self._step_container, on_ready=self._on_step_ready)
            for step_class in steps
        ]

        for step in self._steps:
            step.grid(row=0, column=0, sticky="nsew")
            step.grid_remove()

        self._show_current_step()
        self._invalidate_selector()

    @property
    def step_count(self) -> int:
        """Return total number of steps."""
        return len(self._steps)

    @property
    def current_step_index(self) -> int:
        """Return current step index."""
        return self._current_step_index

    @property
    def current_step(self) -> NavigationStep:
        """Return current step instance."""
        return self._steps[self._current_step_index]

    @property
    def is_first_step(self) -> bool:
        """Return whether current step is the first step."""
        return self._current_step_index == 0

    @property
    def is_last_step(self) -> bool:
        """Return whether current step is the last step."""
        return self._current_step_index == self.step_count - 1

    def prev(self) -> bool:
        """Move to the previous step."""
        if self.is_first_step:
            return False

        self._hide_current_step()
        self._current_step_index -= 1
        self._show_current_step()
        self._invalidate_selector()
        return True

    def next(self) -> bool:
        """Commit current step and move to the next step."""
        if self.is_last_step:
            return False

        if not self.current_step.is_ready:
            return False

        if not self.current_step.commit():
            return False

        self._hide_current_step()
        self._current_step_index += 1
        self._show_current_step()
        self._invalidate_selector()
        return True

    def finish(self) -> bool:
        """Commit current step and notify finish callback."""
        if not self.current_step.is_ready:
            return False

        if not self.current_step.commit():
            return False

        if self._on_finished is not None:
            self._on_finished()

        return True

    def _show_current_step(self) -> None:
        """Show current step."""
        self.current_step.grid()
        self.current_step.tkraise()

    def _hide_current_step(self) -> None:
        """Hide current step."""
        self.current_step.grid_remove()

    def _on_step_ready(self, _: bool) -> None:
        """Refresh selector when current step ready state changes."""
        self._invalidate_selector()

    def _on_selector_clicked(self, select_type: NavigationSelectType) -> None:
        """Handle selector button click."""
        if select_type == NavigationSelectType.PREV:
            self.prev()
            return

        if select_type == NavigationSelectType.NEXT:
            self.next()
            return

        if select_type == NavigationSelectType.FINISH:
            self.finish()
            return

    def _invalidate_selector(self) -> None:
        """Update selector buttons from current navigation state."""
        left: NavigationSelectType | None = None
        right: NavigationSelectType | None = None

        if self.step_count == 1:
            right = NavigationSelectType.FINISH
        elif self.is_first_step:
            right = NavigationSelectType.NEXT
        elif self.is_last_step:
            left = NavigationSelectType.PREV
            right = NavigationSelectType.FINISH
        else:
            left = NavigationSelectType.PREV
            right = NavigationSelectType.NEXT

        self._selector.invalidate(left=left, right=right)