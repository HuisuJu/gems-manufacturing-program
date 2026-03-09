"""
Factory data pool manager.

This module manages the pool directory, metadata lifecycle, status reporting,
and internal raw JSON pull/commit operations used by FactoryDataProvider.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from .retriever import FactoryDataRetriever


class FactoryDataPoolManagerError(Exception):
    """
    Base exception for pool manager failures.
    """


class FactoryDataPoolInactiveError(FactoryDataPoolManagerError):
    """
    Raised when the pool manager is not activated with a valid folder.
    """


class FactoryDataPoolPathError(FactoryDataPoolManagerError):
    """
    Raised when the configured pool path is invalid.
    """


class FactoryDataPoolLeaseError(FactoryDataPoolManagerError):
    """
    Raised when an invalid lease operation is attempted.
    """


class FactoryDataPoolEmptyError(FactoryDataPoolManagerError):
    """
    Raised when no ready factory data file exists in the pool.
    """


@dataclass(frozen=True, slots=True)
class FactoryDataPoolReport:
    """
    Snapshot report of the current factory data pool.
    """

    is_active: bool
    pool_path: Optional[Path]
    total_json_count: int
    ready_count: int
    leased_count: int
    consumed_count: int
    error_count: int

    @property
    def has_json_files(self) -> bool:
        """
        Return whether the pool contains at least one JSON file.
        """
        return self.total_json_count > 0

    @property
    def is_ready(self) -> bool:
        """
        Return whether the pool is active and has at least one ready item.
        """
        return self.is_active and self.ready_count > 0


@dataclass(frozen=True, slots=True)
class FactoryDataPoolLease:
    """
    Raw lease result returned by the pool manager internal pull API.
    """

    file_name: str
    file_path: Path


class FactoryDataPoolManager:
    """
    Manage the factory data pool directory and raw file lease lifecycle.

    Public responsibilities:
        - pool folder path management
        - activation / deactivation
        - metadata initialization and loading
        - report generation
        - optional pool refill via retriever

    Internal responsibilities (provider-only):
        - _pull()
        - _commit(success)

    Notes:
        - Only one leased item is allowed at a time.
        - When an existing metadata file is loaded, any stale "leased" item is
          converted to "error".
        - A path change is rejected while a lease is active.
    """

    STATE_FILE_NAME = ".factory_data_pool_state.json"

    STATUS_READY = "ready"
    STATUS_LEASED = "leased"
    STATUS_CONSUMED = "consumed"
    STATUS_ERROR = "error"

    READY_LOW_WATERMARK = 5
    DEFAULT_REFILL_BATCH_SIZE = 10

    _instance: Optional["FactoryDataPoolManager"] = None

    def __new__(cls, retriever: Optional[FactoryDataRetriever] = None) -> "FactoryDataPoolManager":
        """
        Return the singleton instance.
        """
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self, retriever: Optional[FactoryDataRetriever] = None) -> None:
        """
        Initialize the singleton pool manager.
        """
        if getattr(self, "_initialized", False):
            if retriever is not None:
                self._retriever = retriever
            return

        self._pool_path: Optional[Path] = None
        self._active_leased_file_name: Optional[str] = None
        self._retriever: Optional[FactoryDataRetriever] = retriever
        self._initialized = True

    def set_pool_path(self, pool_path: str | Path | None) -> None:
        """
        Configure the pool folder path.

        Passing None deactivates the pool manager.

        Raises:
            FactoryDataPoolLeaseError:
                A file is currently leased and the path cannot be changed.
            FactoryDataPoolPathError:
                The provided path is invalid.
        """
        if self._active_leased_file_name is not None:
            raise FactoryDataPoolLeaseError(
                "The pool folder cannot be changed while a factory data item is in progress."
            )

        if pool_path is None:
            self._pool_path = None
            return

        resolved = Path(pool_path).expanduser().resolve()
        if not resolved.exists():
            raise FactoryDataPoolPathError(
                "The selected factory data folder does not exist."
            )
        if not resolved.is_dir():
            raise FactoryDataPoolPathError(
                "The selected factory data path is not a folder."
            )

        self._pool_path = resolved
        self._initialize_or_load_pool_state()

    def get_pool_path(self) -> Optional[Path]:
        """
        Return the currently configured pool path.
        """
        return self._pool_path

    def is_active(self) -> bool:
        """
        Return whether the pool manager is active.
        """
        return self._pool_path is not None

    def is_ready(self) -> bool:
        """
        Return whether the pool is active and has at least one ready item.
        """
        return self.get_report().is_ready

    def has_active_lease(self) -> bool:
        """
        Return whether a file is currently leased.
        """
        return self._active_leased_file_name is not None

    def get_report(self) -> FactoryDataPoolReport:
        """
        Return a current report of the pool state.
        """
        if self._pool_path is None:
            return FactoryDataPoolReport(
                is_active=False,
                pool_path=None,
                total_json_count=0,
                ready_count=0,
                leased_count=0,
                consumed_count=0,
                error_count=0,
            )

        state = self._load_and_sync_state()

        ready_count = 0
        leased_count = 0
        consumed_count = 0
        error_count = 0

        for status in state["files"].values():
            if status == self.STATUS_READY:
                ready_count += 1
            elif status == self.STATUS_LEASED:
                leased_count += 1
            elif status == self.STATUS_CONSUMED:
                consumed_count += 1
            elif status == self.STATUS_ERROR:
                error_count += 1

        return FactoryDataPoolReport(
            is_active=True,
            pool_path=self._pool_path,
            total_json_count=len(state["files"]),
            ready_count=ready_count,
            leased_count=leased_count,
            consumed_count=consumed_count,
            error_count=error_count,
        )

    def refill_if_needed(self, fetch_count: int | None = None) -> bool:
        """
        Invoke the configured retriever when the ready count is below the
        low-watermark.

        Args:
            fetch_count:
                Number of files to request from the retriever. If omitted,
                DEFAULT_REFILL_BATCH_SIZE is used.

        Returns:
            True if retrieval was attempted and reported success.
            False if retrieval was not needed or failed.
        """
        pool_path = self._require_active_pool()

        report = self.get_report()
        if report.ready_count >= self.READY_LOW_WATERMARK:
            return False

        if self._retriever is None:
            return False

        target_count = fetch_count if fetch_count is not None else self.DEFAULT_REFILL_BATCH_SIZE
        if target_count <= 0:
            return False

        success = self._retriever.fetch(pool_path, target_count)
        if success:
            self._load_and_sync_state()

        return success

    def set_retriever(self, retriever: Optional[FactoryDataRetriever]) -> None:
        """
        Replace the current retriever implementation.
        """
        self._retriever = retriever

    def get_state_file_path(self) -> Path:
        """
        Return the metadata file path for the active pool.
        """
        pool_path = self._require_active_pool()
        return pool_path / self.STATE_FILE_NAME

    def _pull(self) -> FactoryDataPoolLease:
        """
        Lease one ready raw JSON file from the pool.

        This method is intended to be called only by FactoryDataProvider.

        Returns:
            FactoryDataPoolLease containing the leased file name and path.

        Raises:
            FactoryDataPoolInactiveError:
                The pool is not active.
            FactoryDataPoolLeaseError:
                Another item is already leased.
            FactoryDataPoolEmptyError:
                No ready item is available.
        """
        pool_path = self._require_active_pool()

        if self._active_leased_file_name is not None:
            raise FactoryDataPoolLeaseError(
                "Another factory data item is already in progress."
            )

        state = self._load_and_sync_state()

        leased_items = [
            file_name
            for file_name, status in state["files"].items()
            if status == self.STATUS_LEASED
        ]
        if leased_items:
            raise FactoryDataPoolLeaseError(
                "The pool metadata contains an active leased item. "
                "Complete or recover the current in-progress item first."
            )

        ready_file_name = self._select_next_ready_file_name(state)
        if ready_file_name is None:
            raise FactoryDataPoolEmptyError(
                "No ready factory data file is available in the selected folder."
            )

        state["files"][ready_file_name] = self.STATUS_LEASED
        self._save_state(state)

        self._active_leased_file_name = ready_file_name
        return FactoryDataPoolLease(
            file_name=ready_file_name,
            file_path=pool_path / ready_file_name,
        )

    def _commit(self, success: bool) -> None:
        """
        Finalize the current leased file.

        This method is intended to be called only by FactoryDataProvider.

        Args:
            success:
                True  -> mark leased item as consumed
                False -> mark leased item as error

        Raises:
            FactoryDataPoolInactiveError:
                The pool is not active.
            FactoryDataPoolLeaseError:
                No item is currently leased.
        """
        if self._active_leased_file_name is None:
            raise FactoryDataPoolLeaseError(
                "There is no in-progress factory data item to commit."
            )

        state = self._load_and_sync_state()
        leased_file_name = self._active_leased_file_name

        next_status = self.STATUS_CONSUMED if success else self.STATUS_ERROR
        state["files"][leased_file_name] = next_status
        self._save_state(state)

        self._active_leased_file_name = None

    def _initialize_or_load_pool_state(self) -> None:
        """
        Initialize or load metadata for the active pool.

        Any stale leased item found during activation is converted to error.
        """
        state = self._load_state()
        state = self._sync_state_with_disk(
            state,
            convert_leased_to_error=True,
        )
        self._save_state(state)

    def _load_and_sync_state(self) -> dict[str, Any]:
        """
        Load metadata and synchronize it with the current JSON files on disk.
        """
        state = self._load_state()
        state = self._sync_state_with_disk(
            state,
            convert_leased_to_error=False,
        )
        self._save_state(state)
        return state

    def _load_state(self) -> dict[str, Any]:
        """
        Load metadata from disk.

        If the metadata file does not exist, return a default empty state.
        """
        state_path = self.get_state_file_path()
        if not state_path.exists():
            return {
                "version": 1,
                "files": {},
            }

        with state_path.open("r", encoding="utf-8") as fp:
            raw = json.load(fp)

        if not isinstance(raw, dict):
            return {
                "version": 1,
                "files": {},
            }

        version = raw.get("version", 1)
        if not isinstance(version, int):
            version = 1

        raw_files = raw.get("files", {})
        files: dict[str, str] = {}

        if isinstance(raw_files, dict):
            for file_name, status in raw_files.items():
                if not isinstance(file_name, str):
                    continue
                if not isinstance(status, str):
                    continue
                files[file_name] = status

        return {
            "version": version,
            "files": files,
        }

    def _save_state(self, state: dict[str, Any]) -> None:
        """
        Save metadata to disk atomically.
        """
        state_path = self.get_state_file_path()
        temp_path = state_path.with_suffix(state_path.suffix + ".tmp")

        with temp_path.open("w", encoding="utf-8") as fp:
            json.dump(state, fp, indent=2, ensure_ascii=False, sort_keys=True)
            fp.write("\n")

        temp_path.replace(state_path)

    def _sync_state_with_disk(
        self,
        state: dict[str, Any],
        *,
        convert_leased_to_error: bool,
    ) -> dict[str, Any]:
        """
        Synchronize metadata with the set of JSON files currently present on disk.
        """
        pool_path = self._require_active_pool()

        json_file_names = {
            file_path.name
            for file_path in pool_path.iterdir()
            if file_path.is_file() and file_path.suffix.lower() == ".json"
        }

        allowed_statuses = {
            self.STATUS_READY,
            self.STATUS_LEASED,
            self.STATUS_CONSUMED,
            self.STATUS_ERROR,
        }

        synced_files: dict[str, str] = {}
        existing_files = state.get("files", {})
        if not isinstance(existing_files, dict):
            existing_files = {}

        for file_name in sorted(json_file_names):
            status = self.STATUS_READY

            existing_status = existing_files.get(file_name)
            if isinstance(existing_status, str) and existing_status in allowed_statuses:
                status = existing_status

            if convert_leased_to_error and status == self.STATUS_LEASED:
                status = self.STATUS_ERROR

            synced_files[file_name] = status

        return {
            "version": 1,
            "files": synced_files,
        }

    def _select_next_ready_file_name(self, state: dict[str, Any]) -> Optional[str]:
        """
        Select the next ready file deterministically.
        """
        files = state.get("files", {})
        if not isinstance(files, dict):
            return None

        ready_files = [
            file_name
            for file_name, status in files.items()
            if status == self.STATUS_READY
        ]
        if not ready_files:
            return None

        return sorted(ready_files)[0]

    def _require_active_pool(self) -> Path:
        """
        Return the active pool path or raise an exception.
        """
        if self._pool_path is None:
            raise FactoryDataPoolInactiveError(
                "The factory data pool folder is not selected."
            )
        if not self._pool_path.exists():
            raise FactoryDataPoolPathError(
                "The selected factory data pool folder does not exist."
            )
        if not self._pool_path.is_dir():
            raise FactoryDataPoolPathError(
                "The selected factory data pool path is not a folder."
            )
        return self._pool_path