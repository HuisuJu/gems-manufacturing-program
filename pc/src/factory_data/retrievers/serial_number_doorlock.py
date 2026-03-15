from __future__ import annotations

from typing import AbstractSet, Any

from system import Settings

from ..retriever import Retriever
from ..schema import FactoryDataSchema


class DoorLockSerialNumberRetriever(Retriever):
    """Retriever for door lock serial number factory data."""

    _SUPPORTED_FIELDS = frozenset({"serial_number"})
    _KEY = "doorlock_serial_number"
    _PREFIX = "TMCTAWES"

    _index: int

    def __init__(self) -> None:
        """Initialize retriever."""
        if Settings.has(self._KEY):
            self._index = Settings.get(self._KEY)
        else:
            self._index = 0
            Settings.set(self._KEY, self._index)

    @property
    def name(self) -> str:
        """Return retriever name."""
        return "doorlock serial number retriever"

    @property
    def supported_fields(self) -> AbstractSet[str]:
        """Return fields this retriever can provide."""
        return self._SUPPORTED_FIELDS

    def fetch(self, schema: FactoryDataSchema) -> dict[str, Any]:
        """Fetch requested door lock serial number fields."""
        target_fields = self.target_fields(schema)
        if not target_fields:
            return {}

        result: dict[str, Any] = {}

        if "serial_number" in target_fields:
            result["serial_number"] = self._PREFIX + str(self._index).zfill(4)
            self._index += 1
            Settings.set(self._KEY, self._index)

        return result

    def report(self, is_success: bool) -> None:
        """No-op report hook."""
        _ = is_success
