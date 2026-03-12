from __future__ import annotations

from abc import ABC, abstractmethod

from typing import Any, AbstractSet, Mapping


class RetrieverError(Exception):
    """
    Base retriever error.
    """


class Retriever(ABC):
    """
    Base interface for factory-data retrievers.
    """

    @property
    @abstractmethod

    def name(self) -> str:
        """
        Stable retriever name.
        """
        raise NotImplementedError

    @property
    @abstractmethod

    def supported_fields(self) -> AbstractSet[str]:
        """
        Field names this retriever can provide.
        """
        raise NotImplementedError

    @abstractmethod

    def fetch(self, schema: Mapping[str, Any]) -> dict[str, Any]:
        """
        Fetch factory data from the given schema input.

        Args:
            schema: Schema or constraints used by the retriever.

        Returns:
            Flat field-value mapping.

        Raises:
            RetrieverError: Fetch failed.
        """
        raise NotImplementedError
