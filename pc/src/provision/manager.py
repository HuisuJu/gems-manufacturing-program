"""
Provision manager.

This module orchestrates the provisioning workflow in a dedicated background
thread. It coordinates FactoryDataProvider, ProvisionDispatcher, and
ProvisionReporter, and exposes state changes through an event queue that can be
consumed by the UI thread.
"""

from __future__ import annotations

import queue
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

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


class ProvisionState(str, Enum):
    """
    External provision states exposed to observers.
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
        state:
            Current external workflow state.
        message:
            Human-readable status text.
        dispatcher_ready:
            Current dispatcher readiness.
        start_allowed:
            Whether a new provisioning attempt can be started now.
        finish_allowed:
            Whether the current result can be finalized now.
    """

    state: ProvisionState
    message: str
    dispatcher_ready: bool
    start_allowed: bool
    finish_allowed: bool


@dataclass(slots=True)
class _PendingFinalization:
    """
    Completed provisioning attempt waiting for explicit finalization.
    """

    provider_report_required: bool
    factory_data: dict[str, Any]
    success: bool
    message: str
    started_at: str
    finished_at: str
    dispatcher_name: str
    details: Optional[dict[str, Any]]


class ProvisionManager:
    """
    Provision workflow manager running in a dedicated worker thread.

    Public API:
        - set_dispatcher()
        - set_reporter()
        - start()
        - finish()
        - stop()
        - poll_event()

    Notes:
        - start() is non-blocking and only queues a provisioning request.
        - finish() is non-blocking and finalizes the last completed attempt.
        - Events are queued internally and should be consumed by the UI thread
          using poll_event().
        - Only one provisioning attempt can exist at a time.
        - SUCCESS/FAIL remain visible until finish() is called explicitly.
    """

    def __init__(
        self,
        provider: FactoryDataProvider,
        dispatcher: ProvisionDispatcher | None = None,
        reporter: ProvisionReporter | None = None,
    ) -> None:
        """
        Initialize the provision manager.

        Args:
            provider:
                Factory data provider used for each provisioning attempt.
            dispatcher:
                Active dispatcher implementation.
            reporter:
                Reporter used to persist provisioning results.
        """
        self._provider = provider
        self._dispatcher: ProvisionDispatcher | None = None
        self._reporter = reporter if reporter is not None else ProvisionReporter()

        self._state = _ManagerState.STOPPED
        self._dispatcher_ready = False
        self._pending: _PendingFinalization | None = None

        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._command_queue: queue.Queue[_Command] = queue.Queue()
        self._event_queue: queue.Queue[ProvisionManagerEvent] = queue.Queue()
        self._lock = threading.Lock()

        if dispatcher is not None:
            self.set_dispatcher(dispatcher)

    def set_dispatcher(self, dispatcher: ProvisionDispatcher | None) -> None:
        """
        Set the active dispatcher implementation.

        The manager installs its readiness callback into the dispatcher and
        updates its own readiness snapshot immediately.

        Args:
            dispatcher:
                Dispatcher instance to use, or None to clear it.
        """
        with self._lock:
            self._dispatcher = dispatcher

            if self._dispatcher is not None:
                # The dispatcher base class stores the callback in this field.
                self._dispatcher._ready_listener = self._on_dispatcher_ready_changed
                self._dispatcher_ready = self._dispatcher.is_ready()
            else:
                self._dispatcher_ready = False

            if self._state != _ManagerState.STOPPED:
                self._recompute_idle_like_state_locked()

        self._emit_current_state("Dispatcher configuration updated.")

    def set_reporter(self, reporter: ProvisionReporter) -> None:
        """
        Replace the active reporter implementation.

        Args:
            reporter:
                Reporter instance to use.
        """
        with self._lock:
            self._reporter = reporter

    def start(self) -> None:
        """
        Start the worker thread if needed and request one provisioning attempt.

        Calls outside READY are ignored silently.
        """
        self._ensure_worker_started()

        with self._lock:
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

        self._emit_event(
            ProvisionManagerEvent(
                state=ProvisionState.IDLE,
                message="Provision manager stopped.",
                dispatcher_ready=self._dispatcher_ready,
                start_allowed=False,
                finish_allowed=False,
            )
        )

    def is_running(self) -> bool:
        """
        Return whether the worker thread is currently running.
        """
        thread = self._thread
        return thread is not None and thread.is_alive()

    def poll_event(self, timeout: float | None = None) -> ProvisionManagerEvent | None:
        """
        Poll the next manager event.

        This method is intended to be called by the UI thread.

        Args:
            timeout:
                Maximum seconds to wait. None blocks indefinitely. Zero performs
                a non-blocking poll.

        Returns:
            The next event, or None if the timeout elapsed.
        """
        try:
            return self._event_queue.get(timeout=timeout)
        except queue.Empty:
            return None

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

        self._emit_current_state("Provision manager started.")

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

        self._emit_current_state("Provisioning started.")

        started_at = self._build_iso_utc_now()

        try:
            factory_data = self._provider.pull()
            provider_report_required = True
        except FactoryDataProviderError as exc:
            finished_at = self._build_iso_utc_now()
            self._store_pending_result(
                provider_report_required=False,
                factory_data={},
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
            finished_at = self._build_iso_utc_now()
            self._store_pending_result(
                provider_report_required=provider_report_required,
                factory_data=factory_data,
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
            dispatch_result = dispatcher.dispatch(factory_data)
        except Exception as exc:
            dispatch_result = DispatchResult(
                success=False,
                message=f"Dispatcher error: {type(exc).__name__}: {exc}",
                details=None,
            )

        finished_at = self._build_iso_utc_now()
        self._store_pending_result(
            provider_report_required=provider_report_required,
            factory_data=factory_data,
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

        if pending.provider_report_required:
            try:
                self._provider.report(pending.success)
            except Exception as exc:
                with self._lock:
                    self._pending = None
                    self._recompute_idle_like_state_locked()

                self._emit_current_state(
                    f"Failed to finalize factory data state: {exc}"
                )
                return

        report_write_error: str | None = None

        try:
            self._reporter.write(
                ProvisionReportRecord(
                    index=None,
                    success=pending.success,
                    message=pending.message,
                    dispatcher_name=pending.dispatcher_name,
                    started_at=pending.started_at,
                    finished_at=pending.finished_at,
                    injected_data=pending.factory_data,
                    details=pending.details,
                )
            )
        except ProvisionReporterError as exc:
            report_write_error = str(exc)

        with self._lock:
            self._pending = None
            self._recompute_idle_like_state_locked()

        if report_write_error is not None:
            self._emit_current_state(
                f"{pending.message} Report file write failed: {report_write_error}"
            )
        else:
            self._emit_current_state("Provisioning finalized.")

    def _store_pending_result(
        self,
        provider_report_required: bool,
        factory_data: dict[str, Any],
        dispatch_result: DispatchResult,
        started_at: str,
        finished_at: str,
    ) -> None:
        """
        Store a completed dispatch result and move to waiting-for-finish state.
        """
        pending = _PendingFinalization(
            provider_report_required=provider_report_required,
            factory_data=factory_data,
            success=dispatch_result.success,
            message=dispatch_result.message,
            started_at=started_at,
            finished_at=finished_at,
            dispatcher_name=self._get_dispatcher_name(),
            details=dispatch_result.details,
        )

        with self._lock:
            self._pending = pending
            self._state = (
                _ManagerState.WAITING_FINISH_SUCCESS
                if dispatch_result.success
                else _ManagerState.WAITING_FINISH_FAIL
            )

        self._emit_current_state(dispatch_result.message)

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

        self._emit_current_state("Dispatcher readiness changed.")

    def _recompute_idle_like_state_locked(self) -> None:
        """
        Recompute READY/IDLE state while holding the manager lock.
        """
        self._state = _ManagerState.READY if self._dispatcher_ready else _ManagerState.IDLE

    def _emit_current_state(self, message: str | None = None) -> None:
        """
        Emit the current external state snapshot.
        """
        self._emit_event(self._build_event(message))

    def _build_event(self, message: str | None = None) -> ProvisionManagerEvent:
        """
        Build an external event snapshot from the current internal state.
        """
        with self._lock:
            state = self._state
            dispatcher_ready = self._dispatcher_ready

        if state == _ManagerState.READY:
            return ProvisionManagerEvent(
                state=ProvisionState.READY,
                message=message or "Dispatcher is ready.",
                dispatcher_ready=dispatcher_ready,
                start_allowed=True,
                finish_allowed=False,
            )

        if state == _ManagerState.PROGRESS:
            return ProvisionManagerEvent(
                state=ProvisionState.PROGRESS,
                message=message or "Provisioning in progress.",
                dispatcher_ready=dispatcher_ready,
                start_allowed=False,
                finish_allowed=False,
            )

        if state == _ManagerState.WAITING_FINISH_SUCCESS:
            return ProvisionManagerEvent(
                state=ProvisionState.SUCCESS,
                message=message or "Provisioning completed successfully.",
                dispatcher_ready=dispatcher_ready,
                start_allowed=False,
                finish_allowed=True,
            )

        if state == _ManagerState.WAITING_FINISH_FAIL:
            return ProvisionManagerEvent(
                state=ProvisionState.FAIL,
                message=message or "Provisioning failed.",
                dispatcher_ready=dispatcher_ready,
                start_allowed=False,
                finish_allowed=True,
            )

        return ProvisionManagerEvent(
            state=ProvisionState.IDLE,
            message=message or "Dispatcher is not ready.",
            dispatcher_ready=dispatcher_ready,
            start_allowed=False,
            finish_allowed=False,
        )

    def _emit_event(self, event: ProvisionManagerEvent) -> None:
        """
        Queue one event for consumption by the UI thread.
        """
        self._event_queue.put(event)

    def _get_dispatcher(self) -> ProvisionDispatcher | None:
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