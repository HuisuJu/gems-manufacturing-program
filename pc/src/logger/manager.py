from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from threading import Lock
from typing import Callable


class LogLevel(Enum):
    """Defines supported log severity levels."""

    PROGRESS = 1
    WARNING = 2
    ERROR = 3


@dataclass(slots=True)
class LogRecord:
    """Represents a single log entry."""

    timestamp: datetime
    level: LogLevel
    message: str


class Logger:
    """
    Stores and publishes visible log records.

    The logger keeps only records that pass the currently selected minimum
    level. This means the internal logger state is intentionally aligned
    with what the UI is expected to display.
    """

    _records: deque[LogRecord] = deque()
    _max_records: int = 10000
    _min_level: LogLevel = LogLevel.PROGRESS

    _listeners: list[Callable[[LogRecord], None]] = []
    _lock: Lock = Lock()

    @classmethod
    def set_max_records(cls, max_records: int) -> None:
        """
        Updates the maximum number of retained records.

        If the current number of stored records exceeds the new limit,
        the oldest records are discarded first.

        Args:
            max_records:
                Maximum number of records to retain.

        Raises:
            ValueError:
                Raised when max_records is less than 1.
        """
        if max_records < 1:
            raise ValueError("max_records must be greater than 0.")

        with cls._lock:
            cls._max_records = max_records

            while len(cls._records) > cls._max_records:
                cls._records.popleft()

    @classmethod
    def get_max_records(cls) -> int:
        """
        Returns the maximum number of retained records.
        """
        with cls._lock:
            return cls._max_records

    @classmethod
    def set_min_level(cls, level: LogLevel) -> None:
        """
        Updates the minimum accepted log level.

        Existing records are cleared so that the logger state stays aligned
        with the records that should be visible after the level change.

        Args:
            level:
                New minimum accepted level.
        """
        with cls._lock:
            cls._min_level = level
            cls._records.clear()

    @classmethod
    def get_min_level(cls) -> LogLevel:
        """
        Returns the current minimum accepted log level.
        """
        with cls._lock:
            return cls._min_level

    @classmethod
    def write(cls, level: LogLevel, message: str) -> None:
        """
        Writes a log record if the level passes the current filter.

        Args:
            level:
                Severity level of the log record.
            message:
                User-facing log message.
        """
        with cls._lock:
            if level.value < cls._min_level.value:
                return

            record = LogRecord(
                timestamp=datetime.now(),
                level=level,
                message=message,
            )

            cls._records.append(record)

            if len(cls._records) > cls._max_records:
                cls._records.popleft()

            listeners = list(cls._listeners)

        for listener in listeners:
            try:
                listener(record)
            except Exception:
                pass

    @classmethod
    def get_records(cls) -> list[LogRecord]:
        """
        Returns all currently retained records in ascending time order.
        """
        with cls._lock:
            return list(cls._records)

    @classmethod
    def clear(cls) -> None:
        """
        Clears all retained records.
        """
        with cls._lock:
            cls._records.clear()

    @classmethod
    def subscribe(cls, listener: Callable[[LogRecord], None]) -> None:
        """
        Registers a listener that receives future accepted records.

        Args:
            listener:
                Callback invoked with each accepted LogRecord.
        """
        with cls._lock:
            if listener not in cls._listeners:
                cls._listeners.append(listener)

    @classmethod
    def unsubscribe(cls, listener: Callable[[LogRecord], None]) -> None:
        """
        Unregisters a previously subscribed listener.

        Args:
            listener:
                Listener to remove.
        """
        with cls._lock:
            if listener in cls._listeners:
                cls._listeners.remove(listener)