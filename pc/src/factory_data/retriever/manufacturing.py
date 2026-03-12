from __future__ import annotations

from datetime import datetime

from typing import Any, AbstractSet, Mapping

from .base import Retriever, RetrieverError


class ManufacturingDataRetriever(Retriever):
    """Retriever for manufacturing factory data."""

    _SUPPORTED_FIELDS = frozenset({
        "manufactured_date",
    })

    MANUFACTURED_DATE_FORMAT = "%Y%m%d"

    @property

    def name(self) -> str:
        """Return retriever name."""
        return "manufacturing"

    @property

    def supported_fields(self) -> AbstractSet[str]:
        """Return fields this retriever can provide."""
        return self._SUPPORTED_FIELDS

    def fetch(self, schema: Mapping[str, Any]) -> dict[str, Any]:
        """Fetch requested manufacturing fields."""
        target_fields = self.target_fields(schema)
        if not target_fields:
            return {}

        json: dict[str, Any] = {}

        if "manufactured_date" in target_fields:
            json["manufactured_date"] = self._generate_manufactured_date()

        return json

    def _generate_manufactured_date(self) -> str:
        """Return current date in YYYYMMDD format."""
        return datetime.now().strftime(self.MANUFACTURED_DATE_FORMAT)
