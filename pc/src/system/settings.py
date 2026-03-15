from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from .utils import metadata_folder


class SettingsError(Exception):
    """Base settings error."""


SettingsCallback = Callable[[str, Any], None]


class Settings:
    """Simple JSON-backed key-value settings store."""

    # Settings file location.
    _SETTINGS_FILE_NAME = "settings.json"
    _SETTINGS_FILE_PATH: Path = metadata_folder() / _SETTINGS_FILE_NAME

    # In-memory state.
    _values: dict[str, Any] = {}
    _subscribers: dict[str, list[SettingsCallback]] = {}
    _is_initialized: bool = False

    @classmethod
    def init(cls) -> None:
        """Initialize and load settings."""
        cls._values = {}
        cls._subscribers = {}
        cls._load()
        cls._is_initialized = True

    @classmethod
    def keys(cls) -> list[str]:
        """Return all stored keys."""
        if not cls._is_initialized:
            return []
        return list(cls._values.keys())

    @classmethod
    def has(cls, key: str) -> bool:
        """Return True if key exists."""
        if not cls._is_initialized:
            return False
        return key in cls._values

    @classmethod
    def get(cls, key: str) -> Any:
        """Return value for key, or None if missing."""
        if not cls._is_initialized:
            return None
        return cls._values.get(key, None)

    @classmethod
    def set(cls, key: str, value: Any) -> None:
        """Set value for key, persist it, and notify subscribers on change."""
        if not cls._is_initialized:
            return

        old_value = cls._values.get(key, None)
        if key in cls._values and old_value == value:
            return

        cls._values[key] = value
        cls._save()
        cls._publish(key, value)

    @classmethod
    def clear(cls, key: str) -> None:
        """Clear key value by setting None."""
        if not cls._is_initialized:
            return
        cls.set(key, None)

    @classmethod
    def remove(cls, key: str) -> None:
        """Remove key, persist it, and notify subscribers on change."""
        if not cls._is_initialized:
            return

        if key not in cls._values:
            return

        del cls._values[key]
        cls._save()
        cls._publish(key, None)

    @classmethod
    def subscribe(cls, key: str, callback: SettingsCallback) -> None:
        """Subscribe to changes for a specific key."""
        if not cls._is_initialized:
            return

        subscribers = cls._subscribers.setdefault(key, [])
        if callback not in subscribers:
            subscribers.append(callback)

    @classmethod
    def unsubscribe(cls, key: str, callback: SettingsCallback) -> None:
        """Unsubscribe from changes for a specific key."""
        if not cls._is_initialized:
            return

        subscribers = cls._subscribers.get(key)
        if not subscribers:
            return

        try:
            subscribers.remove(callback)
        except ValueError:
            return

        if not subscribers:
            del cls._subscribers[key]

    @classmethod
    def _publish(cls, key: str, value: Any) -> None:
        """Notify subscribers of a key change."""
        for callback in list(cls._subscribers.get(key, [])):
            try:
                callback(key, value)
            except Exception as exc:
                raise SettingsError(
                    f"Subscriber callback failed for key '{key}'."
                ) from exc

    @classmethod
    def _load(cls) -> None:
        """Load settings from disk, create file if missing."""
        settings_path = cls._SETTINGS_FILE_PATH
        if not settings_path.exists():
            cls._values = {}
            cls._save()
            return

        try:
            with settings_path.open("r", encoding="utf-8") as file:
                raw_data = json.load(file)
        except Exception as exc:
            raise SettingsError(
                f"Failed to read settings from {settings_path}."
            ) from exc

        if not isinstance(raw_data, dict):
            raise SettingsError(
                f"Invalid settings format in {settings_path}: "
                "top-level JSON value must be an object."
            )

        cls._values = raw_data

    @classmethod
    def _save(cls) -> None:
        """Persist current settings to disk."""
        settings_path = cls._SETTINGS_FILE_PATH
        settings_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            with settings_path.open("w", encoding="utf-8") as file:
                json.dump(cls._values, file, ensure_ascii=False, indent=2)
                file.write("\n")
        except Exception as exc:
            raise SettingsError(
                f"Failed to write settings to {settings_path}."
            ) from exc
