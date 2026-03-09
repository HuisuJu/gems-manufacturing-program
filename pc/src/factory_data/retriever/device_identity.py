from __future__ import annotations

from typing import Any, AbstractSet, Mapping

from .base import Retriever, RetrieverError


class DeviceIdentityRetriever(Retriever):
    """
    Retrieve device identity related factory data.

    Currently only provides a placeholder implementation for serial_number.
    The value is generated from an internal incrementing counter.

    The real serial number allocation policy should be implemented later.
    """

    _SUPPORTED_FIELDS = frozenset({
        "serial_number",
    })

    _counter = 1

    @property
    def name(self) -> str:
        """
        Return the logical retriever name.
        """
        return "device_identity"

    @property
    def supported_fields(self) -> AbstractSet[str]:
        """
        Return the field names that this retriever may return.
        """
        return self._SUPPORTED_FIELDS

    def fetch(self, schema: Mapping[str, Any]) -> dict[str, Any]:
        """
        Fetch and return device identity fields requested by the schema.

        Args:
            schema: Factory data schema represented as a Python mapping.

        Returns:
            A dictionary containing the generated serial_number.

        Raises:
            RetrieverError: If the schema does not define a valid required list.
        """
        required_fields = self._get_required_fields(schema)
        target_fields = required_fields & set(self.supported_fields)

        if not target_fields:
            return {}

        result: dict[str, Any] = {}

        if "serial_number" in target_fields:
            result["serial_number"] = self._generate_serial_number()

        return result

    def _get_required_fields(self, schema: Mapping[str, Any]) -> set[str]:
        """
        Return the top-level required field names declared by the schema.
        """
        required = schema.get("required")
        if not isinstance(required, list):
            raise RetrieverError(
                "Factory data schema is missing the top-level required field list."
            )

        return {field for field in required if isinstance(field, str)}

    def _generate_serial_number(self) -> str:
        """
        Generate a placeholder serial number.

        Returns:
            A string representation of an incrementing counter.
        """
        value = self._counter
        self.__class__._counter += 1
        return str(value)