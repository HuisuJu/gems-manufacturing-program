from __future__ import annotations

import copy

from typing import Any, Mapping

from .retriever import Retriever

from .retriever_factory import FactoryDataRetrieverFactory

from .schema import FactoryDataSchema


class FactoryDataProviderError(Exception):
    """Base provider error."""


class FactoryDataProviderInProgressError(FactoryDataProviderError):
    """Raised when pull() is called while previous data is in progress."""


class FactoryDataProviderReportError(FactoryDataProviderError):
    """Raised when report() is called without in-progress data."""


class FactoryDataProvider:
    """Coordinate retrievers and produce merged factory data."""

    def __init__(
        self,
        schema: FactoryDataSchema,
    ) -> None:
        """Initialize provider with resolved schema."""
        self._schema = schema
        self._retrievers: list[Retriever] = (
            FactoryDataRetrieverFactory.create(schema)
        )
        self._in_progress_data: dict[str, Any] | None = None


    def pull(self) -> dict[str, Any]:
        """Pull and merge factory data from all retrievers."""
        if self._in_progress_data is not None:
            raise FactoryDataProviderInProgressError(
                "Factory data is already in progress. "
                "Report it before pulling another one."
            )

        merged: dict[str, Any] = {}
        for retriever in self._retrievers:
            partial = retriever.fetch(self._schema)
            merged.update(partial)

        missing = [
            field
            for field in self._schema.required_fields
            if field not in merged
        ]
        if missing:
            missing_fields = ", ".join(sorted(missing))
            raise FactoryDataProviderError(
                "The pulled factory data is missing required fields: "
                f"{missing_fields}"
            )

        self._in_progress_data = copy.deepcopy(merged)

        return merged

    def report(self, is_success: bool) -> None:
        """Report provisioning result to all retrievers."""
        if self._in_progress_data is None:
            raise FactoryDataProviderReportError(
                "There is no factory data in progress to report."
            )
        
        for retriever in self._retrievers:
            retriever.report(is_success=is_success)

        self._in_progress_data = None
