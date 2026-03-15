from __future__ import annotations

import copy
from typing import Any, ClassVar

from .retriever import Retriever
from .retriever_factory import FactoryDataRetrieverFactory
from .schema import FactoryDataSchema


class FactoryDataProviderError(Exception):
    """Provider error."""


class FactoryDataProviderAlreadyInitializedError(FactoryDataProviderError):
    """Provider is already initialized."""


class FactoryDataProviderInProgressError(FactoryDataProviderError):
    """Previous data is still in progress."""


class FactoryDataProviderReportError(FactoryDataProviderError):
    """No in-progress data to report."""


class FactoryDataProvider:
    """Provide factory data through class-level APIs."""

    _is_initialized: ClassVar[bool] = False
    _schema: ClassVar[FactoryDataSchema | None] = None
    _retrievers: ClassVar[list[Retriever]] = []
    _in_progress_data: ClassVar[dict[str, Any] | None] = None

    def __new__(cls, *args, **kwargs):
        raise TypeError(
            "FactoryDataProvider cannot be instantiated. "
            "Use class-level APIs."
        )

    @classmethod
    def init(cls, schema: FactoryDataSchema) -> None:
        """Initialize the provider."""
        if cls._is_initialized:
            raise FactoryDataProviderAlreadyInitializedError(
                "FactoryDataProvider is already initialized."
            )

        cls._schema = schema
        cls._retrievers = FactoryDataRetrieverFactory.create(schema)
        cls._in_progress_data = None
        cls._is_initialized = True

    @classmethod
    def is_initialized(cls) -> bool:
        """Return whether the provider is initialized."""
        return cls._is_initialized

    @classmethod
    def get_schema(cls) -> FactoryDataSchema | None:
        """Return the current schema."""
        if not cls._is_initialized:
            return None

        return copy.deepcopy(cls._schema)

    @classmethod
    def pull(cls) -> dict[str, Any] | None:
        """Pull one factory data set."""
        if not cls._is_initialized:
            return None

        schema = cls._schema

        if cls._in_progress_data is not None:
            raise FactoryDataProviderInProgressError(
                "Factory data is already in progress."
            )

        merged_data: dict[str, Any] = {}
        for retriever in cls._retrievers:
            partial_data = retriever.fetch(schema)
            merged_data.update(partial_data)

        missing = [
            field for field in schema.required_fields if field not in merged_data
        ]
        if missing:
            missing_fields = ", ".join(sorted(missing))
            raise FactoryDataProviderError(
                f"Missing required fields: {missing_fields}"
            )

        cls._in_progress_data = copy.deepcopy(merged_data)
        return merged_data

    @classmethod
    def report(cls, is_success: bool) -> None:
        """Report the result of the current data set."""
        if not cls._is_initialized:
            return

        if cls._in_progress_data is None:
            raise FactoryDataProviderReportError(
                "There is no factory data in progress."
            )

        try:
            for retriever in cls._retrievers:
                retriever.report(is_success=is_success)
        finally:
            cls._in_progress_data = None
