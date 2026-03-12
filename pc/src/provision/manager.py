"""
Provision manager.

This module orchestrates the provisioning workflow in a dedicated background
thread. It coordinates FactoryDataProvider, ProvisionDispatcher, and
ProvisionReporter, and updates the injected provisioning view directly through
named view triggers.
"""

from __future__ import annotations

import queue

import threading

from datetime import datetime, timezone

from enum import Enum

from typing import Any, Callable, NamedTuple, Optional, Protocol

from factory_data import FactoryDataProvider, FactoryDataProviderError

from logger import Logger, LogLevel

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


class TriggerView(Protocol):
    """Minimal view protocol used by the provision manager."""

    def trigger(self, event_name: str) -> None:
        """Dispatch one named UI event."""


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


class _PendingFinalization(NamedTuple):
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
        - activate()
        - start()
        - finish()
        - stop()

    Notes:
        - start() is non-blocking and only queues a provisioning request.
        - finish() is non-blocking and finalizes the last completed attempt.
        - The injected view is updated through named trigger calls.
        - Only one provisioning attempt can exist at a time.
        - SUCCESS/FAIL remain visible until finish() is called explicitly.
    """

    def __init__(
        self,
        provider: FactoryDataProvider,
        dispatcher: ProvisionDispatcher,
        view: TriggerView,
        reporter: ProvisionReporter | None = None,
        provider_ready_checker: Callable[[], bool] | None = None,
        success_data_publisher: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        """
        Initialize the provision manager.

        Args:
            provider:
                Factory data provider used for each provisioning attempt.
            dispatcher:
                Active dispatcher implementation.
            view:
                Provisioning view updated through trigger() calls.
            reporter:
                Reporter used to persist provisioning results.
            provider_ready_checker:
                Optional callback that returns whether provider-side
                prerequisites are currently satisfied.
            success_data_publisher:
                Optional callback invoked after one successful dispatch.
                Receives the pulled factory data for UI side-effects.
        """
        self._provider = provider
        self._dispatcher = dispatcher
        self._view = view
        self._reporter = reporter if reporter is not None else ProvisionReporter()
        self._provider_ready_checker = provider_ready_checker
        self._success_data_publisher = success_data_publisher

        self._state = _ManagerState.IDLE
        self._dispatcher_ready = self._dispatcher.is_ready()
        self._provider_ready_error_signature: str | None = None
        self._provider_ready = self._evaluate_provider_ready()
        self._pending: _PendingFinalization | None = None

        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._command_queue: queue.Queue[_Command] = queue.Queue()
        self._lock = threading.Lock()

        # Dispatcher base class stores the readiness callback in this field.
        self._dispatcher._ready_listener = self._on_dispatcher_ready_changed

    def activate(self) -> None:
        """
        Activate manager runtime and render initial state.

        This method should be called once after wiring the manager and view.
        It starts the worker thread and pushes the current READY/IDLE state to
        the view immediately.
        """
        self._ensure_worker_started()
        self._refresh_provider_ready()

        with self._lock:
            if self._state in {_ManagerState.IDLE, _ManagerState.READY}:
                self._recompute_idle_like_state_locked()

        self._render_current_state()

    def start(self) -> None:
        """
        Start the worker thread if needed and request one provisioning attempt.

        Calls outside READY are ignored silently.
        """
        self._ensure_worker_started()
        self._refresh_provider_ready()

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

        self._render_idle()

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

        self._render_current_state()

        while not self._stop_event.is_set():
            try:
                command = self._command_queue.get(timeout=0.2)
            except queue.Empty:
                if self._refresh_provider_ready():
                    self._render_current_state()
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

        self._render_progress()

        started_at = self._build_iso_utc_now()

        try:
            factory_data = self._provider.pull()
            provider_report_required = True
        except FactoryDataProviderError:
            finished_at = self._build_iso_utc_now()
            self._store_pending_result(
                provider_report_required=False,
                factory_data={},
                dispatch_result=DispatchResult(
                    success=False,
                    message="Factory data preparation failed.",
                    details=None,
                ),
                started_at=started_at,
                finished_at=finished_at,
            )
            return

        try:
            dispatch_result = self._dispatcher.dispatch(factory_data)
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
                Logger.write(
                    LogLevel.ALERT,
                    "Factory data 사용 결과 저장(report) 중 오류가 발생했습니다. "
                    "현재 작업은 종료 처리되며 다음 작업을 위해 설정/저장소 상태를 확인해 주세요. "
                    f"({type(exc).__name__}: {exc})",
                )
                with self._lock:
                    self._pending = None
                    self._recompute_idle_like_state_locked()

                self._render_current_state()
                return

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
            Logger.write(
                LogLevel.ALERT,
                "프로비저닝 결과 리포트 파일 저장에 실패했습니다. "
                "결과는 화면에 반영되었지만 파일 이력은 남지 않을 수 있습니다. "
                f"({type(exc).__name__}: {exc})",
            )

        with self._lock:
            self._pending = None
            self._recompute_idle_like_state_locked()

        self._render_current_state()

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
            dispatcher_name=type(self._dispatcher).__name__,
            details=dispatch_result.details,
        )

        with self._lock:
            self._pending = pending
            self._state = (
                _ManagerState.WAITING_FINISH_SUCCESS
                if dispatch_result.success
                else _ManagerState.WAITING_FINISH_FAIL
            )

        if dispatch_result.success:
            self._publish_success_data(factory_data)
            self._render_success()
        else:
            self._render_fail()

    def _publish_success_data(self, factory_data: dict[str, Any]) -> None:
        """
        Publish successful factory data to optional UI callback.
        """
        publisher = self._success_data_publisher
        if publisher is None:
            return

        try:
            publisher(factory_data)
        except Exception as exc:
            Logger.write(
                LogLevel.ALERT,
                "성공 결과 후처리 중 오류가 발생했습니다. "
                f"QR 표시 데이터 전달 실패: {type(exc).__name__}: {exc}",
            )

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

        self._render_current_state()

    def _recompute_idle_like_state_locked(self) -> None:
        """
        Recompute READY/IDLE state while holding the manager lock.
        """
        self._state = (
            _ManagerState.READY
            if self._dispatcher_ready and self._provider_ready
            else _ManagerState.IDLE
        )

    def _evaluate_provider_ready(self) -> bool:
        """
        Evaluate provider-side readiness.
        """
        checker = self._provider_ready_checker
        if checker is None:
            return True

        try:
            result = bool(checker())
            self._provider_ready_error_signature = None
            return result
        except Exception as exc:
            signature = f"{type(exc).__name__}:{exc}"
            if self._provider_ready_error_signature != signature:
                Logger.write(
                    LogLevel.ALERT,
                    "프로비저닝 사전조건 확인 중 오류가 발생했습니다. "
                    "START 버튼이 비활성화될 수 있습니다. "
                    f"({type(exc).__name__}: {exc})",
                )
                self._provider_ready_error_signature = signature
            return False

    def _refresh_provider_ready(self) -> bool:
        """
        Refresh provider readiness and update idle-like state if needed.

        Returns:
            True when readiness changed, otherwise False.
        """
        provider_ready = self._evaluate_provider_ready()

        with self._lock:
            changed = provider_ready != self._provider_ready
            self._provider_ready = provider_ready

            if changed and self._state not in {
                _ManagerState.PROGRESS,
                _ManagerState.WAITING_FINISH_SUCCESS,
                _ManagerState.WAITING_FINISH_FAIL,
                _ManagerState.STOPPED,
            }:
                self._recompute_idle_like_state_locked()

        return changed

    def _render_current_state(self) -> None:
        """
        Render the current state to the view.
        """
        with self._lock:
            state = self._state

        if state == _ManagerState.READY:
            self._render_ready()
            return

        if state == _ManagerState.PROGRESS:
            self._render_progress()
            return

        if state == _ManagerState.WAITING_FINISH_SUCCESS:
            self._render_success()
            return

        if state == _ManagerState.WAITING_FINISH_FAIL:
            self._render_fail()
            return

        self._render_idle()

    def _render_idle(self) -> None:
        """
        Render the idle state to the view.
        """
        self._render_dispatcher_status()
        self._safe_trigger("idle")
        self._safe_trigger("disable_start")
        self._safe_trigger("disable_finish")

    def _render_ready(self) -> None:
        """
        Render the ready state to the view.
        """
        self._render_dispatcher_status()
        self._safe_trigger("ready")
        self._safe_trigger("enable_start")
        self._safe_trigger("disable_finish")

    def _render_progress(self) -> None:
        """
        Render the progress state to the view.
        """
        self._render_dispatcher_status()
        self._safe_trigger("progress")
        self._safe_trigger("disable_start")
        self._safe_trigger("disable_finish")

    def _render_success(self) -> None:
        """
        Render the success state to the view.
        """
        self._render_dispatcher_status()
        self._safe_trigger("success")
        self._safe_trigger("disable_start")
        self._safe_trigger("enable_finish")

    def _render_fail(self) -> None:
        """
        Render the failure state to the view.
        """
        self._render_dispatcher_status()
        self._safe_trigger("fail")
        self._safe_trigger("disable_start")
        self._safe_trigger("enable_finish")

    def _render_dispatcher_status(self) -> None:
        """
        Render dispatcher readiness to the view.
        """
        with self._lock:
            dispatcher_ready = self._dispatcher_ready

        if dispatcher_ready:
            self._safe_trigger("dispatcher_ready")
        else:
            self._safe_trigger("dispatcher_not_ready")

    def _safe_trigger(self, event_name: str) -> None:
        """
        Trigger one view event and ignore view-side errors.
        """
        try:
            self._view.trigger(event_name)
        except Exception as exc:
            Logger.write(
                LogLevel.ALERT,
                "화면 상태 갱신 중 오류가 발생했습니다. "
                f"UI 이벤트 '{event_name}' 처리 실패: {type(exc).__name__}: {exc}",
            )
            return

    def _build_iso_utc_now(self) -> str:
        """
        Build an ISO-like UTC timestamp string.
        """
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
