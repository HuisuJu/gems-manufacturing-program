"""
Provision manager.

This module orchestrates the provisioning workflow in a dedicated background
thread. It coordinates FactoryDataProvider, ProvisionDispatcher, and
ProvisionReporter, and notifies external listeners about UI-facing state
changes without depending on any UI framework directly.
"""

from __future__ import annotations

import queue
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Callable, Optional

from factory_data import FactoryDataProvider, FactoryDataProviderError
from .dispatcher import DispatchResult, ProvisionDispatcher
from .reporter import (
    ProvisionReportRecord,
    ProvisionReporter,
    ProvisionReporterError,
)


class ProvisionManagerError(Exception):
    """
    Base exception for provision manager failures.
    """


class ProvisionUIState(str, Enum):
    """
    UI-facing provision states.
    """

    IDLE = "IDLE"
    READY = "READY"
    PROGRESS = "PROGRESS"
    SUCCESS = "SUCCESS"
    FAIL = "FAIL"


class _ManagerState(str, Enum):
    """
    Internal manager states.
    """

    STOPPED = "STOPPED"
    IDLE = "IDLE"
    READY = "READY"
    PROGRESS = "PROGRESS"
    WAITING_FINISH_SUCCESS = "WAITING_FINISH_SUCCESS"
    WAITING_FINISH_FAIL = "WAITING_FINISH_FAIL"


class _Command(str, Enum):
    """
    Commands consumed by the worker thread.
    """

    START = "START"
    FINISH = "FINISH"
    STOP = "STOP"


@dataclass(frozen=True, slots=True)
class ProvisionManagerEvent:
    """
    State notification emitted by ProvisionManager.

    Attributes:
        ui_state:
            UI-facing state.
        button_text:
            Suggested primary button text.
        start_enabled:
            Whether the START action is currently allowed.
        finish_enabled:
            Whether the FINISH action is currently allowed.
        message:
            Human-readable status text for UI display or logs.
        dispatcher_ready:
            Current dispatcher readiness.
    """

    ui_state: ProvisionUIState
    button_text: str
    start_enabled: bool
    finish_enabled: bool
    message: str
    dispatcher_ready: bool


@dataclass(slots=True)
class _PendingFinalization:
    """
    Completed dispatch result waiting for explicit finalization.

    provider_index is None when provisioning failed before FactoryDataProvider
    returned a valid handle.
    """

    provider_index: Optional[int]
    success: bool
    message: str
    started_at: str
    finished_at: str
    dispatcher_name: str
    details: Optional[dict]


EventListener = Callable[[ProvisionManagerEvent], None]


class ProvisionManager:
    """
    Provision workflow manager running in a dedicated worker thread.

    Public API:
        - set_dispatcher()
        - set_reporter()
        - set_event_listener()
        - start()
        - finish()
        - stop()

    Notes:
        - start() is non-blocking and only queues a provisioning request.
        - finish() is non-blocking and finalizes the last completed attempt.
        - Only one provisioning attempt can exist at a time.
        - SUCCESS/FAIL remain visible until finish() is called explicitly.
    """

    _instance: Optional["ProvisionManager"] = None

    def __new__(cls) -> "ProvisionManager":
        """
        Return the singleton instance.
        """
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        """
        Initialize the singleton manager.
        """
        if getattr(self, "_initialized", False):
            return

        self._provider = FactoryDataProvider()
        self._dispatcher: Optional[ProvisionDispatcher] = None
        self._reporter = ProvisionReporter()

        self._event_listener: Optional[EventListener] = None

        self._state = _ManagerState.STOPPED
        self._dispatcher_ready = False
        self._pending: Optional[_PendingFinalization] = None

        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._command_queue: queue.Queue[_Command] = queue.Queue()
        self._lock = threading.Lock()

        self._initialized = True

    def set_dispatcher(self, dispatcher: Optional[ProvisionDispatcher]) -> None:
        """
        Set the active dispatcher implementation.

        The dispatcher readiness listener is reconnected automatically.
        """
        with self._lock:
            if self._dispatcher is not None:
                self._dispatcher.set_ready_listener(None)

            self._dispatcher = dispatcher

            if self._dispatcher is not None:
                self._dispatcher.set_ready_listener(self._on_dispatcher_ready_changed)
                self._dispatcher_ready = self._dispatcher.is_ready()
            else:
                self._dispatcher_ready = False

            if self._state != _ManagerState.STOPPED:
                self._recompute_idle_like_state_locked()

        self._notify_current_state(message="Dispatcher configuration updated.")

    def set_reporter(self, reporter: ProvisionReporter) -> None:
        """
        Replace the active reporter implementation.
        """
        with self._lock:
            self._reporter = reporter

    def set_event_listener(
        self,
        listener: Optional[EventListener],
    ) -> None:
        """
        Register a state listener.

        The listener is invoked whenever the UI-facing state changes.
        """
        with self._lock:
            self._event_listener = listener

    def start(self) -> None:
        """
        Start the manager thread if needed and request one provisioning attempt.

        Duplicate calls during PROGRESS or waiting-for-finish are ignored
        silently.
        """
        self._ensure_worker_started()

        with self._lock:
            if self._state in {
                _ManagerState.PROGRESS,
                _ManagerState.WAITING_FINISH_SUCCESS,
                _ManagerState.WAITING_FINISH_FAIL,
            }:
                return

            if self._state != _ManagerState.READY:
                return

        self._enqueue_command(_Command.START)

    def finish(self) -> None:
        """
        Finalize the most recent SUCCESS/FAIL result.

        Calls outside waiting-for-finish states are ignored silently.
        """
        with self._lock:
            if self._state not in {
                _ManagerState.WAITING_FINISH_SUCCESS,
                _ManagerState.WAITING_FINISH_FAIL,
            }:
                return

        self._enqueue_command(_Command.FINISH)

    def stop(self) -> None:
        """
        Stop the worker thread.

        This method is intended for application shutdown.
        """
        self._enqueue_command(_Command.STOP)
        self._stop_event.set()

        thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=2.0)

        with self._lock:
            self._thread = None
            self._state = _ManagerState.STOPPED

        self._notify_event(
            ProvisionManagerEvent(
                ui_state=ProvisionUIState.IDLE,
                button_text="START",
                start_enabled=False,
                finish_enabled=False,
                message="Provision manager stopped.",
                dispatcher_ready=self._dispatcher_ready,
            )
        )

    def is_running(self) -> bool:
        """
        Return whether the worker thread is currently running.
        """
        thread = self._thread
        return thread is not None and thread.is_alive()

    def _ensure_worker_started(self) -> None:
        """
        Start the worker thread lazily.
        """
        with self._lock:
            thread = self._thread
            if thread is not None and thread.is_alive():
                return

            self._stop_event.clear()
            self._thread = threading.Thread(
                target=self._worker_main,
                name="ProvisionManagerThread",
                daemon=True,
            )
            self._thread.start()

    def _enqueue_command(self, command: _Command) -> None:
        """
        Enqueue a worker command.
        """
        self._command_queue.put(command)

    def _worker_main(self) -> None:
        """
        Worker thread entry point.
        """
        with self._lock:
            self._recompute_idle_like_state_locked()

        self._notify_current_state(message="Provision manager started.")

        while not self._stop_event.is_set():
            try:
                command = self._command_queue.get(timeout=0.2)
            except queue.Empty:
                continue

            if command == _Command.START:
                self._handle_start_command()
            elif command == _Command.FINISH:
                self._handle_finish_command()
            elif command == _Command.STOP:
                break

        with self._lock:
            self._state = _ManagerState.STOPPED

    def _handle_start_command(self) -> None:
        """
        Execute one provisioning attempt.
        """
        with self._lock:
            if self._state != _ManagerState.READY:
                return

            self._state = _ManagerState.PROGRESS

        self._notify_current_state(message="Provisioning started.")

        started_at = self._build_iso_utc_now()

        try:
            result = self._provider.get()
        except FactoryDataProviderError as exc:
            finished_at = self._build_iso_utc_now()
            self._store_pending_result(
                provider_index=None,
                dispatch_result=DispatchResult(
                    success=False,
                    message=str(exc),
                    details=None,
                ),
                started_at=started_at,
                finished_at=finished_at,
            )
            return

        dispatcher = self._get_dispatcher()
        if dispatcher is None:
            try:
                self._provider.report(result.index, success=False)
            except Exception:
                pass

            finished_at = self._build_iso_utc_now()
            self._store_pending_result(
                provider_index=None,
                dispatch_result=DispatchResult(
                    success=False,
                    message="No dispatcher is configured.",
                    details=None,
                ),
                started_at=started_at,
                finished_at=finished_at,
            )
            return

        try:
            dispatch_result = dispatcher.dispatch(result.data)
        except Exception as exc:
            dispatch_result = DispatchResult(
                success=False,
                message=f"Dispatcher error: {type(exc).__name__}: {exc}",
                details=None,
            )

        finished_at = self._build_iso_utc_now()
        self._store_pending_result(
            provider_index=result.index,
            dispatch_result=dispatch_result,
            started_at=started_at,
            finished_at=finished_at,
        )

    def _handle_finish_command(self) -> None:
        """
        Finalize the pending provisioning result.
        """
        with self._lock:
            pending = self._pending
            state = self._state

        if pending is None:
            return

        if state not in {
            _ManagerState.WAITING_FINISH_SUCCESS,
            _ManagerState.WAITING_FINISH_FAIL,
        }:
            return

        report_message = pending.message
        report_write_error: Optional[str] = None

        if pending.provider_index is not None:
            try:
                self._provider.report(
                    pending.provider_index,
                    success=pending.success,
                )
            except Exception as exc:
                with self._lock:
                    self._pending = None
                    self._recompute_idle_like_state_locked()

                self._notify_current_state(
                    message=f"Failed to finalize factory data state: {exc}"
                )
                return

        try:
            self._reporter.write(
                ProvisionReportRecord(
                    index=pending.provider_index,
                    success=pending.success,
                    message=pending.message,
                    dispatcher_name=pending.dispatcher_name,
                    started_at=pending.started_at,
                    finished_at=pending.finished_at,
                    details=pending.details,
                )
            )
        except ProvisionReporterError as exc:
            report_write_error = str(exc)

        with self._lock:
            self._pending = None
            self._recompute_idle_like_state_locked()

        if report_write_error is not None:
            report_message = (
                f"{pending.message} Report file write failed: {report_write_error}"
            )
        else:
            report_message = "Provisioning finalized."

        self._notify_current_state(message=report_message)

    def _store_pending_result(
        self,
        provider_index: Optional[int],
        dispatch_result: DispatchResult,
        started_at: str,
        finished_at: str,
    ) -> None:
        """
        Store a completed dispatch result and move to waiting-for-finish state.
        """
        dispatcher_name = self._get_dispatcher_name()

        pending = _PendingFinalization(
            provider_index=provider_index,
            success=dispatch_result.success,
            message=dispatch_result.message,
            started_at=started_at,
            finished_at=finished_at,
            dispatcher_name=dispatcher_name,
            details=dispatch_result.details,
        )

        with self._lock:
            self._pending = pending
            self._state = (
                _ManagerState.WAITING_FINISH_SUCCESS
                if dispatch_result.success
                else _ManagerState.WAITING_FINISH_FAIL
            )

        self._notify_current_state(message=dispatch_result.message)

    def _on_dispatcher_ready_changed(self, is_ready: bool) -> None:
        """
        Handle dispatcher readiness notifications.
        """
        with self._lock:
            self._dispatcher_ready = is_ready

            if self._state not in {
                _ManagerState.PROGRESS,
                _ManagerState.WAITING_FINISH_SUCCESS,
                _ManagerState.WAITING_FINISH_FAIL,
                _ManagerState.STOPPED,
            }:
                self._recompute_idle_like_state_locked()

        self._notify_current_state(message="Dispatcher readiness changed.")

    def _recompute_idle_like_state_locked(self) -> None:
        """
        Recompute READY/IDLE state while holding the manager lock.
        """
        if self._dispatcher_ready and self._provider.is_ready():
            self._state = _ManagerState.READY
        else:
            self._state = _ManagerState.IDLE

    def _notify_current_state(self, message: Optional[str] = None) -> None:
        """
        Emit the current UI-facing state snapshot.
        """
        event = self._build_event(message=message)
        self._notify_event(event)

    def _build_event(self, message: Optional[str] = None) -> ProvisionManagerEvent:
        """
        Build a UI-facing event snapshot from the current internal state.
        """
        with self._lock:
            state = self._state
            dispatcher_ready = self._dispatcher_ready

        if state == _ManagerState.READY:
            return ProvisionManagerEvent(
                ui_state=ProvisionUIState.READY,
                button_text="START",
                start_enabled=True,
                finish_enabled=False,
                message=message or "Dispatcher is ready.",
                dispatcher_ready=dispatcher_ready,
            )

        if state == _ManagerState.PROGRESS:
            return ProvisionManagerEvent(
                ui_state=ProvisionUIState.PROGRESS,
                button_text="START",
                start_enabled=False,
                finish_enabled=False,
                message=message or "Provisioning in progress.",
                dispatcher_ready=dispatcher_ready,
            )

        if state == _ManagerState.WAITING_FINISH_SUCCESS:
            return ProvisionManagerEvent(
                ui_state=ProvisionUIState.SUCCESS,
                button_text="Finish",
                start_enabled=False,
                finish_enabled=True,
                message=message or "Provisioning completed successfully.",
                dispatcher_ready=dispatcher_ready,
            )

        if state == _ManagerState.WAITING_FINISH_FAIL:
            return ProvisionManagerEvent(
                ui_state=ProvisionUIState.FAIL,
                button_text="Finish",
                start_enabled=False,
                finish_enabled=True,
                message=message or "Provisioning failed.",
                dispatcher_ready=dispatcher_ready,
            )

        if state == _ManagerState.STOPPED:
            return ProvisionManagerEvent(
                ui_state=ProvisionUIState.IDLE,
                button_text="START",
                start_enabled=False,
                finish_enabled=False,
                message=message or "Provision manager stopped.",
                dispatcher_ready=dispatcher_ready,
            )

        return ProvisionManagerEvent(
            ui_state=ProvisionUIState.IDLE,
            button_text="START",
            start_enabled=False,
            finish_enabled=False,
            message=message or "Dispatcher is not ready.",
            dispatcher_ready=dispatcher_ready,
        )

    def _notify_event(self, event: ProvisionManagerEvent) -> None:
        """
        Deliver a state event to the registered listener.
        """
        listener: Optional[EventListener]
        with self._lock:
            listener = self._event_listener

        if listener is None:
            return

        try:
            listener(event)
        except Exception:
            return

    def _get_dispatcher(self) -> Optional[ProvisionDispatcher]:
        """
        Return the current dispatcher.
        """
        with self._lock:
            return self._dispatcher

    def _get_dispatcher_name(self) -> str:
        """
        Return the active dispatcher class name.
        """
        dispatcher = self._get_dispatcher()
        if dispatcher is None:
            return "UnknownDispatcher"
        return type(dispatcher).__name__

    def _build_iso_utc_now(self) -> str:
        """
        Build an ISO-like UTC timestamp string.
        """
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")