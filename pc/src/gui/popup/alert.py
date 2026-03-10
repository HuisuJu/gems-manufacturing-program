from __future__ import annotations

from dataclasses import dataclass
from queue import Empty, Queue
from tkinter import messagebox
from typing import Literal, Optional

import tkinter as tk


AlertLevel = Literal["info", "warning", "error"]


class AlertManagerError(Exception):
    """
    Raised when alert manager lifecycle or runtime operations fail.
    """


@dataclass(frozen=True, slots=True)
class AlertRequest:
    """
    Represents one modal alert request to be shown by the GUI thread.
    """

    level: AlertLevel
    title: str
    message: str


class AlertManager:
    """
    Global alert dispatcher for modal popup messages.

    This manager is intended to be written from any thread and drained only
    from the Tk main thread. The GUI layer must call initialize() once and
    then start() once after the root window is ready.
    """

    _root: Optional[tk.Misc] = None
    _queue: Queue[AlertRequest] = Queue()
    _poll_interval_ms: int = 100
    _max_alerts_per_cycle: int = 4
    _after_id: Optional[str] = None
    _running: bool = False
    _initialized: bool = False

    @classmethod
    def initialize(
        cls,
        root: tk.Misc,
        *,
        poll_interval_ms: int = 100,
        max_alerts_per_cycle: int = 4,
    ) -> None:
        """
        Initializes the alert manager with the Tk root widget.

        Args:
            root:
                Tk root or any widget bound to the main GUI thread.
            poll_interval_ms:
                Queue polling interval in milliseconds.
            max_alerts_per_cycle:
                Maximum number of alerts to process in one polling cycle.
        """
        cls._root = root
        cls._poll_interval_ms = poll_interval_ms
        cls._max_alerts_per_cycle = max_alerts_per_cycle
        cls._initialized = True

    @classmethod
    def start(cls) -> None:
        """
        Starts periodic alert queue polling on the GUI thread.

        Raises:
            AlertManagerError:
                Raised when initialize() has not been called yet.
        """
        if not cls._initialized or cls._root is None:
            raise AlertManagerError("AlertManager is not initialized.")

        if cls._running:
            return

        cls._running = True
        cls._schedule_next_poll()

    @classmethod
    def stop(cls) -> None:
        """
        Stops periodic alert queue polling.
        """
        cls._running = False

        if cls._root is not None and cls._after_id is not None:
            try:
                cls._root.after_cancel(cls._after_id)
            except Exception as exc:
                try:
                    from logger import Logger, LogLevel

                    Logger.write(
                        LogLevel.ALERT,
                        "알림 팝업 스케줄 정리(after_cancel) 중 오류가 발생했습니다. "
                        f"({type(exc).__name__}: {exc})",
                    )
                except Exception:
                    print(
                        "[ALERT_FALLBACK] 알림 팝업 스케줄 정리 오류를 기록하지 못했습니다.",
                        flush=True,
                    )

        cls._after_id = None

    @classmethod
    def publish(cls, level: AlertLevel, title: str, message: str) -> None:
        """
        Enqueues an alert request.

        This method is thread-safe and may be called from non-GUI threads.

        Args:
            level:
                Alert severity level.
            title:
                Popup title.
            message:
                Popup body text.
        """
        cls._queue.put(
            AlertRequest(
                level=level,
                title=title,
                message=message,
            )
        )

    @classmethod
    def info(cls, title: str, message: str) -> None:
        """
        Enqueues an informational alert.
        """
        cls.publish("info", title, message)

    @classmethod
    def warning(cls, title: str, message: str) -> None:
        """
        Enqueues a warning alert.
        """
        cls.publish("warning", title, message)

    @classmethod
    def error(cls, title: str, message: str) -> None:
        """
        Enqueues an error alert.
        """
        cls.publish("error", title, message)

    @classmethod
    def _schedule_next_poll(cls) -> None:
        """
        Schedules the next polling cycle.
        """
        if not cls._running or cls._root is None:
            return

        cls._after_id = cls._root.after(
            cls._poll_interval_ms,
            cls._drain_queue,
        )

    @classmethod
    def _drain_queue(cls) -> None:
        """
        Drains queued alerts and shows them synchronously on the GUI thread.
        """
        cls._after_id = None

        if not cls._running or cls._root is None:
            return

        processed = 0

        while processed < cls._max_alerts_per_cycle:
            try:
                request = cls._queue.get_nowait()
            except Empty:
                break

            cls._show(request)
            processed += 1

        cls._schedule_next_poll()

    @classmethod
    def _show(cls, request: AlertRequest) -> None:
        """
        Displays one modal alert.
        """
        if cls._root is None:
            return

        if request.level == "info":
            messagebox.showinfo(
                title=request.title,
                message=request.message,
                parent=cls._root,
            )
            return

        if request.level == "warning":
            messagebox.showwarning(
                title=request.title,
                message=request.message,
                parent=cls._root,
            )
            return

        messagebox.showerror(
            title=request.title,
            message=request.message,
            parent=cls._root,
        )
