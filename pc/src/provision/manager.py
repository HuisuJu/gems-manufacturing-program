"""Provision manager."""

from __future__ import annotations
import queue
import threading
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, ClassVar, NamedTuple

from factory_data import FactoryDataProvider, FactoryDataProviderError
from logger import Logger, LogLevel
from .dispatcher import ProvisionDispatcher
from .reporter import ProvisionReporter, ProvisionReporterError


class ProvisionManagerError(Exception):
    """Base provision manager error."""

class ProvisionManagerEvent(str, Enum):
    """Events published to subscribers (e.g., UI)."""
    IDLE = "idle"
    READY = "ready"
    PROGRESS = "progress"
    SUCCESS = "success"
    FAIL = "fail"
    ENABLE_START = "enable_start"
    DISABLE_START = "disable_start"
    ENABLE_FINISH = "enable_finish"
    DISABLE_FINISH = "disable_finish"
    DISPATCHER_READY = "dispatcher_ready"
    DISPATCHER_NOT_READY = "dispatcher_not_ready"

ProvisionManagerEventListener = Callable[[ProvisionManagerEvent], None]

class _ManagerState(str, Enum):
    """Internal lifecycle states."""
    STOPPED = "STOPPED"
    IDLE = "IDLE"
    READY = "READY"
    PROGRESS = "PROGRESS"
    WAITING_FINISH_SUCCESS = "WAITING_FINISH_SUCCESS"
    WAITING_FINISH_FAIL = "WAITING_FINISH_FAIL"

class _Command(str, Enum):
    """Worker thread commands."""
    START = "START"
    FINISH = "FINISH"
    STOP = "STOP"

class _PendingFinalization(NamedTuple):
    factory_data: dict[str, Any]
    success: bool
    message: str
    started_at: str
    finished_at: str
    dispatcher_name: str
    details: dict[str, Any] | None

class ProvisionManager:
    """Manage provisioning workflow through class-level APIs."""

    _lock = threading.Lock()
    _registry_lock = threading.RLock()
    
    _dispatcher: ClassVar[ProvisionDispatcher | None] = None
    _registered_dispatcher: ClassVar[ProvisionDispatcher | None] = None
    _reporter = ProvisionReporter
    _event_listeners: ClassVar[list[ProvisionManagerEventListener]] = []

    _state = _ManagerState.STOPPED
    _dispatcher_ready = False
    _dispatcher_ready_error_signature: ClassVar[str | None] = None
    _pending: ClassVar[_PendingFinalization | None] = None

    _thread: ClassVar[threading.Thread | None] = None
    _stop_event = threading.Event()
    _command_queue: ClassVar[queue.Queue[_Command]] = queue.Queue()

    def __new__(cls, *args, **kwargs):
        raise TypeError("ProvisionManager cannot be instantiated. Use class-level APIs.")

    # --- Public API ---

    @classmethod
    def register_dispatcher(cls, dispatcher: ProvisionDispatcher) -> None:
        with cls._lock: cls._dispatcher = dispatcher
        with cls._registry_lock: cls._registered_dispatcher = dispatcher
        cls._refresh_dispatcher_ready()
        cls._sync_and_render()

    @classmethod
    def get_stream(cls):
        with cls._registry_lock:
            return cls._registered_dispatcher.stream if cls._registered_dispatcher else None

    @classmethod
    def subscribe_event(cls, listener: ProvisionManagerEventListener) -> None:
        with cls._lock:
            if listener not in cls._event_listeners: cls._event_listeners.append(listener)

    @classmethod
    def unsubscribe_event(cls, listener: ProvisionManagerEventListener) -> None:
        with cls._lock:
            if listener in cls._event_listeners: cls._event_listeners.remove(listener)

    @classmethod
    def activate(cls) -> None:
        cls._ensure_worker_started()
        cls._refresh_dispatcher_ready()
        with cls._lock:
            if cls._state in {_ManagerState.IDLE, _ManagerState.READY, _ManagerState.STOPPED}:
                cls._update_idle_state_locked()
        cls._sync_and_render()

    @classmethod
    def start(cls) -> None:
        cls._ensure_worker_started()
        if cls._refresh_dispatcher_ready() or cls._state == _ManagerState.READY:
            cls._enqueue_command(_Command.START)

    @classmethod
    def finish(cls) -> None:
        with cls._lock:
            if cls._state in {_ManagerState.WAITING_FINISH_SUCCESS, _ManagerState.WAITING_FINISH_FAIL}:
                cls._enqueue_command(_Command.FINISH)

    @classmethod
    def stop(cls) -> None:
        cls._enqueue_command(_Command.STOP)
        cls._stop_event.set()
        if cls._thread and cls._thread.is_alive(): cls._thread.join(timeout=2.0)
        with cls._lock:
            cls._thread, cls._pending, cls._state = None, None, _ManagerState.STOPPED
        cls._sync_and_render()

    @classmethod
    def _ensure_worker_started(cls) -> None:
        with cls._lock:
            if cls._thread and cls._thread.is_alive():
                return

            cls._stop_event.clear()
            cls._thread = threading.Thread(
                target=cls._worker_main,
                name="ProvisionManagerThread",
                daemon=True,
            )
            cls._thread.start()

    @classmethod
    def _enqueue_command(cls, command: _Command) -> None:
        cls._command_queue.put(command)

    # --- Internal Logic ---

    @classmethod
    def _sync_and_render(cls) -> None:
        """Publish events to bridge the internal state to the widget layer."""
        with cls._lock:
            state, ready = cls._state, cls._dispatcher_ready

        # Dispatcher Status
        cls._publish_event(ProvisionManagerEvent.DISPATCHER_READY if ready else ProvisionManagerEvent.DISPATCHER_NOT_READY)

        # Main State Event Mapping
        mapping = {
            _ManagerState.IDLE: (ProvisionManagerEvent.IDLE, False, False),
            _ManagerState.READY: (ProvisionManagerEvent.READY, True, False),
            _ManagerState.PROGRESS: (ProvisionManagerEvent.PROGRESS, False, False),
            _ManagerState.WAITING_FINISH_SUCCESS: (ProvisionManagerEvent.SUCCESS, False, True),
            _ManagerState.WAITING_FINISH_FAIL: (ProvisionManagerEvent.FAIL, False, True),
            _ManagerState.STOPPED: (ProvisionManagerEvent.IDLE, False, False),
        }
        main_evt, start_en, finish_en = mapping.get(state, (ProvisionManagerEvent.IDLE, False, False))
        
        cls._publish_event(main_evt)
        cls._publish_event(ProvisionManagerEvent.ENABLE_START if start_en else ProvisionManagerEvent.DISABLE_START)
        cls._publish_event(ProvisionManagerEvent.ENABLE_FINISH if finish_en else ProvisionManagerEvent.DISABLE_FINISH)

    @classmethod
    def _worker_main(cls) -> None:
        with cls._lock: cls._update_idle_state_locked()
        cls._sync_and_render()

        while not cls._stop_event.is_set():
            try:
                cmd = cls._command_queue.get(timeout=0.2)
                if cmd == _Command.START: cls._run_provisioning()
                elif cmd == _Command.FINISH: cls._run_finalization()
                elif cmd == _Command.STOP: break
            except queue.Empty:
                if cls._refresh_dispatcher_ready(): cls._sync_and_render()

    @classmethod
    def _run_provisioning(cls) -> None:
        with cls._lock:
            if cls._state != _ManagerState.READY: return
            cls._state = _ManagerState.PROGRESS
        cls._sync_and_render()

        start_time = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        
        try:
            data = FactoryDataProvider.pull()
            if not data:
                cls._store_result({}, False, "FactoryDataProvider not initialized", start_time)
                return
            
            success = cls._dispatcher.dispatch(data) if cls._dispatcher else False
            msg = "Success" if success else "Dispatch failed"
        except Exception as e:
            data, success, msg = {}, False, f"Execution Error: {type(e).__name__}"

        cls._store_result(data, success, msg, start_time)

    @classmethod
    def _store_result(cls, data, success, msg, start_time) -> None:
        with cls._lock:
            cls._pending = _PendingFinalization(
                factory_data=data, success=success, message=msg,
                started_at=start_time, finished_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                dispatcher_name=type(cls._dispatcher).__name__ if cls._dispatcher else "None",
                details=None
            )
            cls._state = _ManagerState.WAITING_FINISH_SUCCESS if success else _ManagerState.WAITING_FINISH_FAIL
        cls._sync_and_render()

    @classmethod
    def _run_finalization(cls) -> None:
        with cls._lock:
            pending = cls._pending
            if not pending: return

        # Perform IO/Reporting
        try: FactoryDataProvider.report(pending.success)
        except Exception as e: Logger.write(LogLevel.ALERT, f"Provider report failed: {e}")

        try:
            cls._reporter.write({
                "success": pending.success, "message": pending.message, "dispatcher": pending.dispatcher_name,
                "started_at": pending.started_at, "finished_at": pending.finished_at,
                "injected_data": pending.factory_data, "details": pending.details, "index": None
            })
        except Exception as e: Logger.write(LogLevel.ALERT, f"Report file save failed: {e}")

        with cls._lock:
            cls._pending = None
            cls._update_idle_state_locked()
        cls._sync_and_render()

    @classmethod
    def _update_idle_state_locked(cls) -> None:
        cls._state = _ManagerState.READY if cls._dispatcher_ready else _ManagerState.IDLE

    @classmethod
    def _refresh_dispatcher_ready(cls) -> bool:
        is_ready = False
        if cls._dispatcher:
            try:
                is_ready = bool(cls._dispatcher.stream.is_connected())
                cls._dispatcher_ready_error_signature = None
            except Exception as e:
                sig = f"{type(e).__name__}:{e}"
                if cls._dispatcher_ready_error_signature != sig:
                    Logger.write(LogLevel.ALERT, f"Readiness check failed: {e}")
                    cls._dispatcher_ready_error_signature = sig

        with cls._lock:
            changed = (is_ready != cls._dispatcher_ready)
            cls._dispatcher_ready = is_ready
            if changed and cls._state in {_ManagerState.IDLE, _ManagerState.READY}:
                cls._update_idle_state_locked()
        return changed

    @classmethod
    def _publish_event(cls, event: ProvisionManagerEvent) -> None:
        with cls._lock: listeners = list(cls._event_listeners)
        for listener in listeners:
            try: listener(event)
            except Exception as e: Logger.write(LogLevel.ALERT, f"Event delivery failed: {e}")
