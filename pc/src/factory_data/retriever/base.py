from __future__ import annotations

from abc import ABC, abstractmethod

from typing import Any, AbstractSet, Mapping


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

    def target_fields(self, schema: Mapping[str, Any]) -> set[str]:
        """Return fields this retriever needs to fetch for the schema."""
        required: list[Any] = schema.get("required", [])
        required_fields = {field for field in required if isinstance(field, str)}

        return required_fields & set(self.supported_fields)

    @abstractmethod

    def fetch(self, schema: Mapping[str, Any]) -> dict[str, Any]:
        """Fetch factory data for requested schema fields."""
        raise NotImplementedError
