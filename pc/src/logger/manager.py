from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from queue import Queue
from threading import Lock, Thread
from typing import Callable, Optional


class LogLevel(Enum):
    """Log severity levels."""

    DEBUG = 1
    WARNING = 2
    ERROR = 3
    ALERT = 4


@dataclass(slots=True)
class LogRecord:
    """One log item."""

    timestamp: datetime
    level: LogLevel
    message: str


class Logger:
    """Async logger that publishes records to listeners."""

    _min_level: LogLevel = LogLevel.DEBUG
    _listeners: list[Callable[[LogRecord], None]] = []

    _lock: Lock = Lock()
    _queue: Queue[Optional[LogRecord]] = Queue()
    _worker: Optional[Thread] = None
    _running: bool = False

    @classmethod
    def start(cls) -> None:
        """Start worker thread if needed."""
        with cls._lock:
            if cls._running and cls._worker is not None and cls._worker.is_alive():
                return

            cls._running = True
            cls._worker = Thread(
                target=cls._worker_main,
                name="LoggerWorker",
                daemon=True,
            )
            cls._worker.start()

    @classmethod
    def stop(cls, timeout_sec: float = 1.0) -> None:
        """Stop worker thread."""
        with cls._lock:
            if cls._worker is None or not cls._worker.is_alive():
                cls._running = False
                return

            cls._queue.put(None)

        cls._worker.join(timeout=timeout_sec)
        cls._running = False

    @classmethod
    def set_min_level(cls, level: LogLevel) -> None:
        """Set minimum accepted level."""
        with cls._lock:
            cls._min_level = level

    @classmethod
    def get_min_level(cls) -> LogLevel:
        """Return current minimum accepted level."""
        with cls._lock:
            return cls._min_level

    @classmethod
    def write(cls, level: LogLevel, message: str) -> None:
        """Queue one log write request."""
        with cls._lock:
            if not cls._running or cls._worker is None or not cls._worker.is_alive():
                return

        cls._queue.put(
            LogRecord(
                timestamp=datetime.now(),
                level=level,
                message=message,
            )
        )

    @classmethod
    def subscribe(cls, listener: Callable[[LogRecord], None]) -> None:
        """Register a record listener."""
        with cls._lock:
            if listener not in cls._listeners:
                cls._listeners.append(listener)

    @classmethod
    def unsubscribe(cls, listener: Callable[[LogRecord], None]) -> None:
        """Remove a record listener."""
        with cls._lock:
            if listener in cls._listeners:
                cls._listeners.remove(listener)

    @classmethod
    def _worker_main(cls) -> None:
        """Process queued writes in background."""
        while True:
            record = cls._queue.get()

            if record is None:
                cls._queue.task_done()
                break

            try:
                with cls._lock:
                    listeners: list[Callable[[LogRecord], None]] = []
                    if record.level.value >= cls._min_level.value:
                        listeners = list(cls._listeners)

                if not listeners:
                    # fallback console output
                    ts = record.timestamp.strftime("%Y-%m-%d %H:%M:%S")
                    print(f"[{ts}] [{record.level.name}] {record.message}")
                    continue

                for listener in listeners:
                    try:
                        listener(record)
                    except Exception:
                        pass

            finally:
                cls._queue.task_done()
