from __future__ import annotations

from datetime import datetime
from typing import Any, AbstractSet, Mapping

from .base import Retriever, RetrieverError


class ManufacturingDataRetriever(Retriever):
    """
    Retrieve manufacturing-related factory data.

    At this time, this retriever provides only the manufactured_date field.
    The value uses the first 8 characters of the manufacturing information
    format and is encoded as YYYYMMDD.
    """

    _SUPPORTED_FIELDS = frozenset({
        "manufactured_date",
    })

    DATE_FORMAT = "%Y%m%d"

    @property
    def name(self) -> str:
        """
        Return the logical retriever name.
        """
        return "manufacturing"

    @property
    def supported_fields(self) -> AbstractSet[str]:
        """
        Return the field names that this retriever may return.
        """
        return self._SUPPORTED_FIELDS

    def fetch(self, schema: Mapping[str, Any]) -> dict[str, Any]:
        """
        Fetch and return manufacturing-related fields requested by the schema.

        Currently, only manufactured_date is supported. The returned value is
        an 8-character string in YYYYMMDD format.

        Args:
            schema: Factory data schema represented as a Python mapping.

        Returns:
            A flat dictionary containing manufacturing-related fields.

        Raises:
            RetrieverError: If the schema does not define a valid required list.
        """
        required_fields = self._get_required_fields(schema)
        target_fields = required_fields & set(self.supported_fields)

        if not target_fields:
            return {}

        result: dict[str, Any] = {}

        if "manufactured_date" in target_fields:
            result["manufactured_date"] = self._generate_manufactured_date()

        return result

    def _get_required_fields(self, schema: Mapping[str, Any]) -> set[str]:
        """
        Return the top-level required field names declared by the schema.

        Args:
            schema: Factory data schema represented as a Python mapping.

        Returns:
            A set of required field names.

        Raises:
            RetrieverError: If the schema does not define a valid required list.
        """
        required = schema.get("required")
        if not isinstance(required, list):
            raise RetrieverError(
                "Factory data schema is missing the top-level required field list."
            )

        return {field for field in required if isinstance(field, str)}

    def _generate_manufactured_date(self) -> str:
        """
        Generate the manufacturing date string.

        Returns:
            An 8-character manufacturing date string in YYYYMMDD format.
        """
        return datetime.now().strftime(self.DATE_FORMAT)