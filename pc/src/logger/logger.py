from typing import Callable
from dataclasses import dataclass
from enum import Enum
from collections import deque
from datetime import datetime
import threading


class LogLevel(Enum):
    PROGRESS = 1
    WARNING  = 2
    ERROR    = 3


@dataclass(slots=True)
class LogRecord:
    timestamp: datetime
    level: LogLevel
    message: str


class Logger:
    records: deque[LogRecord] = deque()
    max_records = 10000

    listeners: list[Callable[[LogRecord], None]] = list()
    lock = threading.Lock()

    @classmethod
    def configure(cls, max_records: int = 10000) -> None:
        cls.max_records = max_records

    @classmethod
    def write(cls, level: LogLevel, message: str) -> None:
        record = LogRecord(
            timestamp=datetime.now(),
            level=level,
            message=message)
        
        with cls.lock:
            cls.records.append(record)

            if len(cls.records) > cls.max_records:
                cls.records.popleft()

        for listener in cls.listeners:
            try:
                listener(record)
            except Exception:
                pass

    @classmethod
    def get_records(
        cls,
        level: LogLevel,
        start_time: datetime,
        finish_time: datetime
    ) -> list[LogRecord]:
        with cls.lock:
            records = list(cls.records)

        filtered_records: list[LogRecord] = []

        for record in records:
            if record.level.value < level.value:
                continue
            if record.timestamp < start_time:
                continue
            if record.timestamp > finish_time:
                continue

            filtered_records.append(record)

        return filtered_records

    @classmethod
    def clear(cls) -> None:
        with cls.lock:
            cls.records.clear()

    @classmethod
    def subscribe(cls, listener: Callable[[LogRecord], None]) -> None:
        with cls.lock:
            cls.listeners.append(listener)

    @classmethod
    def unsubscribe(cls, listener: Callable[[LogRecord], None]) -> None:
        with cls.lock:
            if listener in cls.listeners:
                cls.listeners.remove(listener)
