from __future__ import annotations

from abc import ABC, abstractmethod
from typing import AbstractSet, Any

from .schema import FactoryDataSchema


class RetrieverError(Exception):
    """Base retriever error."""


class Retriever(ABC):
    """Interface for factory-data retrievers."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Return retriever name."""
        raise NotImplementedError

    @property
    @abstractmethod
    def supported_fields(self) -> AbstractSet[str]:
        """Return fields this retriever can provide."""
        raise NotImplementedError

    def target_fields(self, schema: FactoryDataSchema) -> set[str]:
        """Return fields this retriever needs to fetch for the schema."""
        return set(schema.required_fields) & set(self.supported_fields)

    @abstractmethod
    def fetch(self, schema: FactoryDataSchema) -> dict[str, Any]:
        """Fetch factory data for requested schema fields."""
        raise NotImplementedError

    @abstractmethod
    def report(self, is_success: bool) -> None:
        """Report the result of the fetch operation."""
        raise NotImplementedError
