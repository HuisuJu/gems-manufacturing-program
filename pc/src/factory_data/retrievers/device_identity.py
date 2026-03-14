from __future__ import annotations

from typing import AbstractSet, Any

from ..retriever import Retriever

from ..schema import FactoryDataSchema


class DeviceIdentityRetriever(Retriever):
    """Retriever for device identity factory data."""

    _SUPPORTED_FIELDS = frozenset({
        "serial_number",
    })

    _counter = 1

    @property

    def name(self) -> str:
        """Return retriever name."""
        return "device_identity"

    @property

    def supported_fields(self) -> AbstractSet[str]:
        """Return fields this retriever can provide."""
        return self._SUPPORTED_FIELDS

    def fetch(self, schema: FactoryDataSchema) -> dict[str, Any]:
        """Fetch requested device identity fields."""
        target_fields = self.target_fields(schema)
        if not target_fields:
            return {}

        json: dict[str, Any] = {}

        if "serial_number" in target_fields:
            json["serial_number"] = self._generate_serial_number()

        return json

    def report(self, is_success: bool) -> None:
        """No-op report hook."""
        _ = is_success

    def _generate_serial_number(self) -> str:
        """Generate serial number string."""
        value = self._counter
        DeviceIdentityRetriever._counter += 1
        return str(value)
