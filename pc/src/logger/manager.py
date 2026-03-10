from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from queue import Empty, Queue
from threading import Lock, Thread
from typing import Callable, Optional

from gui.popup.alert import AlertManager


class LogLevel(Enum):
    """Defines supported log severity levels."""

    PROGRESS = 1
    WARNING = 2
    ERROR = 3
    ALERT = 4


@dataclass(slots=True)
class LogRecord:
    """Represents a single log entry."""

    timestamp: datetime
    level: LogLevel
    message: str


@dataclass(slots=True)
class _WriteRequest:
    """Represents one asynchronous logger write request."""

    timestamp: datetime
    level: LogLevel
    message: str


class Logger:
    """
    Stores and publishes visible log records asynchronously.

    Public write requests are enqueued immediately and processed by a dedicated
    worker thread. The logger lifecycle is controlled explicitly through
    start() and stop().
    """

    _records: deque[LogRecord] = deque()
    _max_records: int = 10000
    _min_level: LogLevel = LogLevel.PROGRESS

    _listeners: list[Callable[[LogRecord], None]] = []
    _lock: Lock = Lock()

    _queue: Queue[Optional[_WriteRequest]] = Queue()
    _worker: Optional[Thread] = None
    _running: bool = False
    _worker_lock: Lock = Lock()

    @classmethod
    def start(cls) -> None:
        """
        Starts the logger worker thread.

        This method is idempotent.
        """
        with cls._worker_lock:
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
    def stop(cls, *, drain: bool = True, timeout: float = 2.0) -> None:
        """
        Stops the logger worker thread.

        Args:
            drain:
                If True, waits for queued messages to be processed before exit.
            timeout:
                Maximum join timeout in seconds.
        """
        with cls._worker_lock:
            worker = cls._worker
            if worker is None:
                cls._running = False
                return

            if drain:
                cls.flush()

            cls._running = False
            cls._queue.put(None)

        worker.join(timeout=timeout)

        with cls._worker_lock:
            if cls._worker is worker:
                cls._worker = None

    @classmethod
    def flush(cls, timeout_sec: float = 2.0) -> None:
        """
        Blocks until all currently queued log writes are processed.

        Args:
            timeout_sec:
                Maximum wait time in seconds.

        Raises:
            RuntimeError:
                Raised when the logger is not running.
            TimeoutError:
                Raised when the queue is not drained within the timeout.
        """
        import time

        with cls._worker_lock:
            if not cls._running:
                raise RuntimeError("Logger has not been started.")

        deadline = time.monotonic() + timeout_sec
        while time.monotonic() < deadline:
            if cls._queue.empty():
                return
            time.sleep(0.01)

        raise TimeoutError("Logger flush timed out.")

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
        Enqueues a log write request and returns immediately.

        Args:
            level:
                Severity level of the log record.
            message:
                User-facing log message.

        Raises:
            RuntimeError:
                Raised when the logger has not been started.
        """
        with cls._worker_lock:
            if not cls._running or cls._worker is None or not cls._worker.is_alive():
                raise RuntimeError("Logger has not been started.")

        cls._queue.put(
            _WriteRequest(
                timestamp=datetime.now(),
                level=level,
                message=message,
            )
        )

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

    @classmethod
    def _worker_main(cls) -> None:
        """
        Processes queued log write requests in the background.
        """
        while True:
            try:
                request = cls._queue.get(timeout=0.1)
            except Empty:
                if not cls._running:
                    break
                continue

            if request is None:
                cls._queue.task_done()
                break

            try:
                cls._process_write(request)
            finally:
                cls._queue.task_done()

    @classmethod
    def _process_write(cls, request: _WriteRequest) -> None:
        """
        Converts one write request into logger state updates and notifications.
        """
        record = LogRecord(
            timestamp=request.timestamp,
            level=request.level,
            message=request.message,
        )

        is_alert = request.level == LogLevel.ALERT

        with cls._lock:
            accepted = is_alert or (request.level.value >= cls._min_level.value)

            if accepted:
                cls._records.append(record)

                if len(cls._records) > cls._max_records:
                    cls._records.popleft()

                listeners = list(cls._listeners)
            else:
                listeners = []

        if is_alert:
            AlertManager.error("Alert", request.message)

        for listener in listeners:
            try:
                listener(record)
            except Exception as exc:
                AlertManager.error(
                    "Alert",
                    "로그 리스너 처리 중 오류가 발생했습니다. "
                    "화면 로그 업데이트가 일부 누락될 수 있습니다. "
                    f"({type(exc).__name__}: {exc})",
                )
