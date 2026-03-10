from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Callable


class SettingsError(Exception):
    """
    Base exception for settings failures.
    """


class SettingsValidationError(SettingsError):
    """
    Raised when a setting value is invalid.
    """


class ModelName(str, Enum):
    """
    Supported product models.
    """

    DOORLOCK = "doorlock"
    THERMOSTAT = "thermostat"
    EMULATOR = "emulator"


class SettingsItem(str, Enum):
    """
    Supported settings items.
    """

    MODEL_NAME = "model_name"
    DAC_POOL_DIR_PATH = "dac_pool_dir_path"
    PAI_FILE_PATH = "pai_file_path"
    CD_FILE_PATH = "cd_file_path"
    REPORT_FILE_PATH = "report_file_path"


SettingsCallback = Callable[[SettingsItem, object | None], None]


class Settings:
    """
    Hold application settings and notify subscribers when settings change.

    Managed settings:
    - model_name
    - dac_pool_dir_path
    - pai_file_path
    - cd_file_path
    - report_file_path
    """

    def __init__(self) -> None:
        """
        Initialize an empty settings object.
        """
        self._values: dict[SettingsItem, object | None] = {
            SettingsItem.MODEL_NAME: None,
            SettingsItem.DAC_POOL_DIR_PATH: None,
            SettingsItem.PAI_FILE_PATH: None,
            SettingsItem.CD_FILE_PATH: None,
            SettingsItem.REPORT_FILE_PATH: None,
        }

        self._subscribers: dict[SettingsItem, list[SettingsCallback]] = {
            SettingsItem.MODEL_NAME: [],
            SettingsItem.DAC_POOL_DIR_PATH: [],
            SettingsItem.PAI_FILE_PATH: [],
            SettingsItem.CD_FILE_PATH: [],
            SettingsItem.REPORT_FILE_PATH: [],
        }

    def get(self, item: SettingsItem) -> object | None:
        """
        Return the current value of a settings item.

        Args:
            item: Settings item to read.

        Returns:
            The current item value, or None if not configured.
        """
        return self._values[item]

    def set(self, item: SettingsItem, value: object | None) -> None:
        """
        Set a settings item value.

        Args:
            item: Settings item to update.
            value: New value. None clears the item.

        Raises:
            SettingsValidationError: If the provided value is invalid.
        """
        resolved = self._normalize_value(item, value)

        if self._values[item] == resolved:
            return

        self._values[item] = resolved
        self._notify_subscribers(item, resolved)

    def clear(self, item: SettingsItem) -> None:
        """
        Clear a settings item.

        Args:
            item: Settings item to clear.
        """
        self.set(item, None)

    def subscribe(self, item: SettingsItem, callback: SettingsCallback) -> None:
        """
        Register a callback for a specific settings item.

        Duplicate callbacks are ignored.

        Args:
            item: The settings item to observe.
            callback: Callback receiving the changed item and its new value.
        """
        subscribers = self._subscribers[item]
        if callback not in subscribers:
            subscribers.append(callback)

    def unsubscribe(self, item: SettingsItem, callback: SettingsCallback) -> None:
        """
        Unregister a callback for a specific settings item.

        Args:
            item: The observed settings item.
            callback: Callback to remove.
        """
        subscribers = self._subscribers[item]
        if callback in subscribers:
            subscribers.remove(callback)

    def _notify_subscribers(self, item: SettingsItem, value: object | None) -> None:
        """
        Notify subscribers of a changed settings item.

        Args:
            item: The changed settings item.
            value: The new value.
        """
        for callback in tuple(self._subscribers[item]):
            callback(item, value)

    def _normalize_value(self, item: SettingsItem, value: object | None) -> object | None:
        """
        Normalize and validate a settings item value.

        Args:
            item: Settings item to validate.
            value: Candidate value.

        Returns:
            The normalized value.

        Raises:
            SettingsValidationError: If the value is invalid.
        """
        if item == SettingsItem.MODEL_NAME:
            return self._normalize_model_name(value)

        if item == SettingsItem.DAC_POOL_DIR_PATH:
            return self._normalize_directory_path(
                path=value,
                field_name="DAC pool directory",
            )

        if item == SettingsItem.PAI_FILE_PATH:
            return self._normalize_file_path(
                path=value,
                field_name="PAI file",
            )

        if item == SettingsItem.CD_FILE_PATH:
            return self._normalize_file_path(
                path=value,
                field_name="CD file",
            )

        if item == SettingsItem.REPORT_FILE_PATH:
            return self._normalize_output_file_path(
                path=value,
                field_name="Report file",
            )

        raise SettingsValidationError(f"Unsupported settings item: {item}")

    def _normalize_model_name(self, value: object | None) -> ModelName | None:
        """
        Normalize and validate a model name value.

        Args:
            value: Model name value.

        Returns:
            The normalized ModelName value, or None.
        """
        if value is None:
            return None

        if isinstance(value, ModelName):
            return value

        if not isinstance(value, str):
            raise SettingsValidationError("The model name is invalid.")

        normalized = value.strip().lower()
        if not normalized:
            raise SettingsValidationError("The model name must not be empty.")

        try:
            return ModelName(normalized)
        except ValueError as exc:
            raise SettingsValidationError(
                f"Unsupported model name: {value}"
            ) from exc

    def _normalize_directory_path(
        self,
        path: object | None,
        field_name: str,
    ) -> Path | None:
        """
        Normalize and validate a directory path.

        Args:
            path: Directory path value.
            field_name: Human-readable field name.

        Returns:
            A resolved Path or None.
        """
        if path is None:
            return None

        if not isinstance(path, (str, Path)):
            raise SettingsValidationError(f"The selected {field_name} is invalid.")

        resolved = Path(path).expanduser().resolve()

        if not resolved.exists():
            raise SettingsValidationError(f"The selected {field_name} does not exist.")

        if not resolved.is_dir():
            raise SettingsValidationError(f"The selected {field_name} is not a directory.")

        return resolved

    def _normalize_file_path(
        self,
        path: object | None,
        field_name: str,
    ) -> Path | None:
        """
        Normalize and validate an existing file path.

        Args:
            path: File path value.
            field_name: Human-readable field name.

        Returns:
            A resolved Path or None.
        """
        if path is None:
            return None

        if not isinstance(path, (str, Path)):
            raise SettingsValidationError(f"The selected {field_name} is invalid.")

        resolved = Path(path).expanduser().resolve()

        if not resolved.exists():
            raise SettingsValidationError(f"The selected {field_name} does not exist.")

        if not resolved.is_file():
            raise SettingsValidationError(f"The selected {field_name} is not a file.")

        return resolved

    def _normalize_output_file_path(
        self,
        path: object | None,
        field_name: str,
    ) -> Path | None:
        """
        Normalize and validate an output file path.

        The file itself does not need to exist, but its parent directory must
        exist and must be a directory.

        Args:
            path: Output file path value.
            field_name: Human-readable field name.

        Returns:
            A resolved Path or None.
        """
        if path is None:
            return None

        if not isinstance(path, (str, Path)):
            raise SettingsValidationError(f"The selected {field_name} is invalid.")

        resolved = Path(path).expanduser().resolve()
        parent = resolved.parent

        if not parent.exists():
            raise SettingsValidationError(
                f"The parent directory of the selected {field_name} does not exist."
            )

        if not parent.is_dir():
            raise SettingsValidationError(
                f"The parent path of the selected {field_name} is not a directory."
            )

        return resolved


settings = Settings()