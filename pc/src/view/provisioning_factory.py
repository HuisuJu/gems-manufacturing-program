from __future__ import annotations

import tkinter as tk
from enum import Enum
from typing import Mapping

from .base import View, ViewCallback


class ProvisioningViewKey(str, Enum):
    """
    Supported provisioning view callback keys.
    """

    IDLE = "idle"
    READY = "ready"
    PROGRESS = "progress"
    SUCCESS = "success"
    FAIL = "fail"

    DISPATCHER_READY = "dispatcher_ready"
    DISPATCHER_NOT_READY = "dispatcher_not_ready"

    ENABLE_START = "enable_start"
    DISABLE_START = "disable_start"

    ENABLE_FINISH = "enable_finish"
    DISABLE_FINISH = "disable_finish"


def create_provisioning_view(
    window: tk.Misc,
    callbacks: Mapping[ProvisioningViewKey | str, ViewCallback],
) -> View:
    """
    Create a provisioning-specific View instance.

    Args:
        window:
            Tkinter/customtkinter root or widget exposing after().
        callbacks:
            Mapping from provisioning view key to callback.

    Returns:
        Configured View instance.
    """
    normalized_callbacks: dict[str, ViewCallback] = {}

    for key, callback in callbacks.items():
        if isinstance(key, ProvisioningViewKey):
            normalized_callbacks[key.value] = callback
        else:
            normalized_callbacks[str(key)] = callback

    return View(
        window=window,
        callbacks=normalized_callbacks,
    )