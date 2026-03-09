"""
Factory data provider.

This module exposes the public provisioning-facing API. It obtains raw JSON
files from FactoryDataPoolManager, parses them, augments the payload with
runtime-generated fields, and provides an index-based handle to the caller.
"""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

from .pool_manager import (
    FactoryDataPoolEmptyError,
    FactoryDataPoolLeaseError,
    FactoryDataPoolManager,
    FactoryDataPoolManagerError,
)


class FactoryDataProviderError(Exception):
    """
    Base exception for factory data provider failures.
    """


class FactoryDataProviderInProgressError(FactoryDataProviderError):
    """
    Raised when get() is called while a previous item has not been reported yet.
    """


class FactoryDataProviderHandleError(FactoryDataProviderError):
    """
    Raised when an invalid handle is passed to report().
    """


@dataclass(frozen=True, slots=True)
class FactoryDataGetResult:
    """
    Result returned by FactoryDataProvider.get().

    Attributes:
        index:
            Runtime-local handle for the current in-flight item.
        data:
            Fully prepared factory data payload.
    """

    index: int
    data: dict[str, Any]


@dataclass(slots=True)
class _InFlightItem:
    """
    Internal in-flight provider state.
    """

    index: int


class FactoryDataProvider:
    """
    Public provider facade for factory data.

    Lifecycle:
        1. get()    -> returns augmented payload with a runtime handle
        2. report() -> finalizes the current in-flight item

    Notes:
        - Only one in-flight item is allowed at a time.
        - report() must be called before the next get().
        - The runtime index handle is process-local and resets on program start.
    """

    _instance: Optional["FactoryDataProvider"] = None

    def __new__(cls) -> "FactoryDataProvider":
        """
        Return the singleton instance.
        """
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        """
        Initialize the singleton provider.
        """
        if getattr(self, "_initialized", False):
            return

        self._pool_manager = FactoryDataPoolManager()
        self._next_index = 0
        self._in_flight: Optional[_InFlightItem] = None
        self._initialized = True

    def is_ready(self) -> bool:
        """
        Return whether the provider can serve a new item.
        """
        return self._in_flight is None and self._pool_manager.is_ready()

    def has_in_flight_item(self) -> bool:
        """
        Return whether an item is currently in progress.
        """
        return self._in_flight is not None

    def get(self) -> FactoryDataGetResult:
        """
        Get one fully prepared factory data payload.

        Returns:
            FactoryDataGetResult containing a runtime-local index and the
            augmented payload.

        Raises:
            FactoryDataProviderInProgressError:
                A previous item has not been reported yet.
            FactoryDataProviderError:
                The pool item could not be loaded or prepared.
        """
        if self._in_flight is not None:
            raise FactoryDataProviderInProgressError(
                "The previous factory data item has not been reported yet."
            )

        try:
            lease = self._pool_manager._pull()
        except FactoryDataPoolEmptyError as exc:
            raise FactoryDataProviderError(
                "No ready factory data is available."
            ) from exc
        except FactoryDataPoolLeaseError as exc:
            raise FactoryDataProviderError(
                "Another factory data item is already in progress."
            ) from exc
        except FactoryDataPoolManagerError as exc:
            raise FactoryDataProviderError(
                "Failed to obtain factory data from the pool."
            ) from exc

        try:
            with lease.file_path.open("r", encoding="utf-8") as fp:
                payload = json.load(fp)

            if not isinstance(payload, dict):
                raise FactoryDataProviderError(
                    "The selected factory data file must contain a JSON object at the top level."
                )

            prepared_payload = self._augment_payload(payload)

        except json.JSONDecodeError as exc:
            self._safe_commit_failure()
            raise FactoryDataProviderError(
                "The selected factory data file is not a valid JSON file."
            ) from exc
        except FactoryDataProviderError:
            self._safe_commit_failure()
            raise
        except Exception as exc:
            self._safe_commit_failure()
            raise FactoryDataProviderError(
                f'Failed to load factory data from "{lease.file_name}".'
            ) from exc

        index = self._allocate_index()
        self._in_flight = _InFlightItem(index=index)

        return FactoryDataGetResult(
            index=index,
            data=prepared_payload,
        )

    def report(self, index: int, success: bool) -> None:
        """
        Report the result of the current in-flight factory data item.

        Args:
            index:
                Runtime-local handle returned by get().
            success:
                True  -> mark the item as consumed
                False -> mark the item as error

        Raises:
            FactoryDataProviderHandleError:
                No item is in progress or the index does not match.
            FactoryDataProviderError:
                The result could not be reflected to the pool state.
        """
        if self._in_flight is None:
            raise FactoryDataProviderHandleError(
                "There is no in-progress factory data item to report."
            )

        if index != self._in_flight.index:
            raise FactoryDataProviderHandleError(
                "The provided factory data handle does not match the current in-progress item."
            )

        try:
            self._pool_manager._commit(success=success)
        except FactoryDataPoolManagerError as exc:
            raise FactoryDataProviderError(
                "Failed to update the factory data pool state."
            ) from exc
        finally:
            self._in_flight = None

    def _allocate_index(self) -> int:
        """
        Allocate the next runtime-local handle.
        """
        self._next_index += 1
        return self._next_index

    def _augment_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        """
        Create the final payload by adding runtime-generated fields.

        The original JSON file content is treated as immutable.
        """
        result = copy.deepcopy(payload)
        result["manufactured_date"] = self._build_manufactured_date()
        return result

    def _build_manufactured_date(self) -> str:
        """
        Build a UTC manufacturing timestamp string.
        """
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    def _safe_commit_failure(self) -> None:
        """
        Mark the current leased pool item as failed.

        This method is used when get() fails after the pool manager has already
        leased a file. Best effort is applied to avoid hiding the original
        exception.
        """
        try:
            self._pool_manager._commit(success=False)
        except Exception:
            pass