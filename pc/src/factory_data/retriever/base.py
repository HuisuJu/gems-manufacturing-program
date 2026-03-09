from __future__ import annotations

from abc import ABC, abstractmethod

from typing import Any, AbstractSet, Mapping


class RetrieverError(Exception):
    """
    Common error type for retriever implementations.

    Raise this (or a subclass) when data acquisition fails in a way that
    callers can handle as a retriever-level failure.
    """


class Retriever(ABC):
    """
    Interface for components that acquire factory data fields.

    Implementation contract:
    - `fetch()` receives a schema-like mapping as input.
    - `fetch()` returns a flat dictionary (`str -> Any`).
    - Returned keys must be a subset of `supported_fields`.
    - Implementations should not depend on other retrievers' output.
    """

    @property
    @abstractmethod

    def name(self) -> str:
        """
        Stable retriever identifier used for logging and diagnostics.
        """
        raise NotImplementedError

    @property
    @abstractmethod

    def supported_fields(self) -> AbstractSet[str]:
        """
        Flat field names that this retriever can provide.
        """
        raise NotImplementedError

    @abstractmethod

    def fetch(self, schema: Mapping[str, Any]) -> dict[str, Any]:
        """
        Acquire data for fields supported by this retriever.

        Output rules:
        - Return a flat dictionary only.
        - Include only keys declared in `supported_fields`.
        - Returning a subset is valid when some values are unavailable.

        Args:
            schema: Input schema/constraints for the acquisition process.

        Returns:
            Flat field-value mapping produced by this retriever.

        Raises:
            RetrieverError: Data acquisition failed.
        """
        raise NotImplementedError
