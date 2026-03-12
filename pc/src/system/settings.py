from __future__ import annotations

import json

from dataclasses import dataclass

from enum import Enum

from pathlib import Path

from typing import Any, Callable, Generic, TypeVar, cast

from .utils import program_metadata_path


class SettingsError(Exception):
    """Base settings error."""


class SettingsTypeError(SettingsError):
    """Raised when a setting value has an invalid type."""


class SettingsSerializationError(SettingsError):
    """Raised when settings cannot be serialized or deserialized."""


class ModelName(str, Enum):
    """Supported models."""

    DOORLOCK    = "doorlock"
    THERMOSTAT  = "thermostat"
    EMULATOR    = "emulator"


class SettingsItem(str, Enum):
    """Settings items."""

    MODEL_NAME        = "model-name"
    DAC_POOL_DIR_PATH = "dac-pool-dir-path"
    PAI_FILE_PATH     = "pai-file-path"
    CD_FILE_PATH      = "cd-file-path"


SettingsValue = Any
SettingsCallback = Callable[[SettingsItem, Any], None]

T = TypeVar("T")


@dataclass(frozen=True)


class SettingSpec(Generic[T]):
    """Serialization and type rules for one setting item."""

    type: type[Any]
    decoder: Callable[[Any], T]
    encoder: Callable[[T], Any]


def _decode_model_name(raw: Any) -> ModelName | None:
    if raw is None:
        return None
    try:
        return ModelName(str(raw))
    except ValueError:
        return None


def _encode_model_name(value: ModelName | None) -> str | None:
    if value is None:
        return None
    return value.value


def _decode_path(raw: Any) -> Path | None:
    if raw is None:
        return None
    try:
        return Path(str(raw)).expanduser().resolve()
    except Exception:
        return None


def _encode_path(value: Path | None) -> str | None:
    if value is None:
        return None
    return str(value)


class Settings:
    """Global settings store."""

    _SETTINGS_FILE_NAME = "settings.json"
    _SETTINGS_FILE_PATH: Path = program_metadata_path() / _SETTINGS_FILE_NAME

    _SPECS: dict[SettingsItem, SettingSpec[Any]] = {
        SettingsItem.MODEL_NAME: SettingSpec[ModelName | None](
            type=ModelName,
            decoder=_decode_model_name,
            encoder=_encode_model_name,
        ),
        SettingsItem.DAC_POOL_DIR_PATH: SettingSpec[Path | None](
            type=Path,
            decoder=_decode_path,
            encoder=_encode_path,
        ),
        SettingsItem.PAI_FILE_PATH: SettingSpec[Path | None](
            type=Path,
            decoder=_decode_path,
            encoder=_encode_path,
        ),
        SettingsItem.CD_FILE_PATH: SettingSpec[Path | None](
            type=Path,
            decoder=_decode_path,
            encoder=_encode_path,
        ),
    }

    _values: dict[SettingsItem, SettingsValue] = {}
    _subscribers: dict[SettingsItem, list[SettingsCallback]] = {}
    _initialized: bool = False

    @classmethod

    def init(cls) -> None:
        """Initialize settings storage."""
        cls._values = {item: None for item in SettingsItem}
        cls._subscribers = {item: [] for item in SettingsItem}
        cls._load()
        cls._initialized = True

    @classmethod

    def get(cls, item: SettingsItem) -> Any:
        """Return the raw value for a setting item."""
        if not cls._initialized:
            return None
        return cls._values[item]

    @classmethod

    def set(cls, item: SettingsItem, value: Any) -> None:
        """Set a setting value."""
        if not cls._initialized:
            return

        if cls._values[item] == value:
            return

        cls._values[item] = value
        cls._save()

        for callback in tuple(cls._subscribers[item]):
            callback(item, value)

    @classmethod

    def clear(cls, item: SettingsItem) -> None:
        """Clear a setting value."""
        if not cls._initialized:
            return
        cls.set(item, None)

    @classmethod

    def subscribe(cls, item: SettingsItem, callback: SettingsCallback) -> None:
        """Subscribe to changes for a specific setting."""
        if not cls._initialized:
            return

        subscribers = cls._subscribers[item]
        if callback not in subscribers:
            subscribers.append(callback)

    @classmethod

    def unsubscribe(cls, item: SettingsItem, callback: SettingsCallback) -> None:
        """Unsubscribe from changes for a specific setting."""
        if not cls._initialized:
            return

        subscribers = cls._subscribers[item]
        if callback in subscribers:
            subscribers.remove(callback)

    @classmethod

    def _load(cls) -> None:
        """Load settings from the JSON file."""
        settings_path = cls._SETTINGS_FILE_PATH
        if not settings_path.exists():
            return

        try:
            with settings_path.open("r", encoding="utf-8") as file:
                raw_data = json.load(file)
                if not isinstance(raw_data, dict):
                    raise SettingsSerializationError(
                        f"Invalid settings format in {settings_path}: "
                        "top-level JSON value must be an object."
                    )
        except SettingsSerializationError:
            raise
        except Exception as exc:
            raise SettingsSerializationError(
                f"Failed to read settings from {settings_path}."
            ) from exc

        for item, spec in cls._SPECS.items():
            raw_value = raw_data.get(item.value)
            decoded = spec.decoder(raw_value)
            if decoded is not None and not isinstance(decoded, spec.type):
                decoded = None

            cls._values[item] = decoded

    @classmethod

    def _save(cls) -> None:
        """Save settings to the JSON file."""
        settings_path = cls._SETTINGS_FILE_PATH
        settings_path.parent.mkdir(parents=True, exist_ok=True)

        encoded: dict[str, Any] = {}
        for item, value in cls._values.items():
            spec = cls._SPECS[item]
            try:
                encoded[item.value] = spec.encoder(cast(Any, value))
            except Exception:
                encoded[item.value] = value

        try:
            with settings_path.open("w", encoding="utf-8") as file:
                json.dump(encoded, file, ensure_ascii=False, indent=2)
                file.write("\n")
        except Exception as exc:
            raise SettingsSerializationError(
                f"Failed to write settings to {settings_path}."
            ) from exc
