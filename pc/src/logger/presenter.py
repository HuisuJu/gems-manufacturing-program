from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from enum import Enum
from typing import Sequence, TextIO

from .manager import LogLevel, LogRecord


class LogPresenterType(Enum):
    """Defines the available log presenter types."""

    TEXT = "text"


class LogPresenter(ABC):
    """
    Abstract base class for log presenters.

    A presenter writes already collected log records to an opened output
    stream using a concrete presentation format.
    """

    def save(
        self,
        records: Sequence[LogRecord],
        file: TextIO,
    ) -> None:
        """
        Writes the provided records to the opened file object.

        Args:
            records:
                Log records to store.
            file:
                Opened writable text file object.
        """
        self._save_records(
            records=records,
            file=file,
        )

    def _format_timestamp(self, timestamp: datetime) -> str:
        """
        Converts a datetime value into a stable display string.
        """
        return timestamp.strftime("%Y-%m-%d %H:%M:%S")

    def _format_level(self, level: LogLevel) -> str:
        """
        Converts a log level enum into a display string.
        """
        return level.name

    @abstractmethod
    def _save_records(
        self,
        records: Sequence[LogRecord],
        file: TextIO,
    ) -> None:
        """
        Writes the given records using the presenter-specific format.

        Args:
            records:
                Records to store.
            file:
                Opened writable text file object.
        """
        raise NotImplementedError


class LogTextPresenter(LogPresenter):
    """
    Writes log records in a plain text format.
    """

    def _save_records(
        self,
        records: Sequence[LogRecord],
        file: TextIO,
    ) -> None:
        """
        Writes log records to a text file.

        Args:
            records:
                Records to store.
            file:
                Opened writable text file object.
        """
        file.write("Log Report\n")
        file.write("=" * 80 + "\n")
        file.write(f"Generated At : {self._format_timestamp(datetime.now())}\n")
        file.write(f"Record Count : {len(records)}\n")
        file.write("\n")

        file.write("Records\n")
        file.write("-" * 80 + "\n")

        for record in records:
            file.write(
                f"[{self._format_timestamp(record.timestamp)}] "
                f"[{self._format_level(record.level)}] "
                f"{record.message}\n"
            )