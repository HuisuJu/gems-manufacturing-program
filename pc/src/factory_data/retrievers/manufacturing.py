from __future__ import annotations

from datetime import datetime
from typing import AbstractSet, Any

from ..retriever import Retriever
from ..schema import FactoryDataSchema


class ManufacturingDataRetriever(Retriever):
    """Retriever for manufactured date."""

    _SUPPORTED_FIELDS = frozenset({"manufactured_date"})
    MANUFACTURED_DATE_FORMAT = "%Y%m%d"

    @property
    def name(self) -> str:
        # Retriever name
        return "manufacturing"

    @property
    def supported_fields(self) -> AbstractSet[str]:
        # Supported fields
        return self._SUPPORTED_FIELDS

    def fetch(self, schema: FactoryDataSchema) -> dict[str, Any]:
        # Return manufactured date
        target_fields = self.target_fields(schema)
        if not target_fields:
            return {}

        result: dict[str, Any] = {}
        if "manufactured_date" in target_fields:
            result["manufactured_date"] = self._generate_manufactured_date()
        return result

    def report(self, is_success: bool) -> None:
        # No-op
        _ = is_success

    def _generate_manufactured_date(self) -> str:
        # Return today's date in YYYYMMDD format
        return datetime.now().strftime(self.MANUFACTURED_DATE_FORMAT)
