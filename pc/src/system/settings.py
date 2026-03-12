from __future__ import annotations

from enum import Enum, IntEnum

from typing import Callable


class SettingsError(Exception):
    """
    Base settings error.
    """


class SettingsValidationError(SettingsError):
    """
    Raised for invalid setting values.
    """


class ModelName(str, Enum):
    """
    Supported models.
    """

    DOORLOCK   = 'doorlock'
    THERMOSTAT = 'thermostat'
    EMULATOR   = 'emulator'


class SettingsItem(IntEnum):
    """
    Available settings keys.
    """

    MODEL_NAME         = 1
    DAC_POOL_DIR_PATH  = 2
    PAI_FILE_PATH      = 3
    CD_FILE_PATH       = 4


SettingsCallback = Callable[[SettingsItem, object | None], None]


class Settings:
    """
    Settings store with subscriber notifications.
    """

    _values: dict[SettingsItem, object | None] = {}
    _subscribers: dict[SettingsItem, list[SettingsCallback]] = {}

    @classmethod

    def init(cls) -> None:
        """
        Initialize storage once.
        """
        cls._values = {
            SettingsItem.MODEL_NAME: None,
            SettingsItem.DAC_POOL_DIR_PATH: None,
            SettingsItem.PAI_FILE_PATH: None,
            SettingsItem.CD_FILE_PATH: None,
        }

        cls._subscribers = {
            SettingsItem.MODEL_NAME: [],
            SettingsItem.DAC_POOL_DIR_PATH: [],
            SettingsItem.PAI_FILE_PATH: [],
            SettingsItem.CD_FILE_PATH: [],
        }

    @classmethod

    def get(cls, item: SettingsItem) -> object | None:
        """
        Return current value for one item.
        """
        return cls._values[item]

    @classmethod

    def set(cls, item: SettingsItem, value: object | None) -> None:
        """
        Set one item value.
        """
        if item not in cls._values:
            raise SettingsError(f'Unsupported settings item: {item!r}')

        if cls._values[item] == value:
            return

        cls._values[item] = value

        for callback in tuple(cls._subscribers[item]):
            callback(item, value)

    @classmethod

    def clear(cls, item: SettingsItem) -> None:
        """
        Clear one item value.
        """
        cls.set(item, None)

    @classmethod

    def subscribe(cls, item: SettingsItem, callback: SettingsCallback) -> None:
        """
        Register callback for one item.
        """
        subscribers = cls._subscribers[item]
        if callback not in subscribers:
            subscribers.append(callback)

    @classmethod

    def unsubscribe(cls, item: SettingsItem, callback: SettingsCallback) -> None:
        """
        Unregister callback for one item.
        """
        subscribers = cls._subscribers[item]
        if callback in subscribers:
            subscribers.remove(callback)
