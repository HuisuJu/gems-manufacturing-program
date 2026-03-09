"""
Emulator dispatcher.

This module provides a concrete ProvisionDispatcher implementation for local
testing without a real device transport. The emulator consumes the full payload,
simulates a provisioning delay, and returns a synthetic DispatchResult.
"""

from __future__ import annotations

import json

import time

from typing import Any, Optional

from logger import Logger, LogLevel

from provision import DispatchResult, ProvisionDispatcher


class _PayloadStats:
    """
    Recursive payload traversal statistics.
    """

    def __init__(self) -> None:
        self.dict_count = 0
        self.list_count = 0
        self.scalar_count = 0
        self.key_count = 0


class EmulatorDispatcher(ProvisionDispatcher):
    """
    Provision dispatcher implementation for local testing.

    Notes:
        - The dispatcher traverses the full payload recursively so that no field
          is ignored during emulation.
        - dispatch() is synchronous and blocks for a configurable delay.
        - The next dispatch result can be forced to succeed or fail.
    """

    def __init__(
        self,
        *,
        initial_ready: bool = True,
        dispatch_delay_sec: float = 1.0,
        default_success: bool = True,
    ) -> None:
        """
        Initialize the emulator dispatcher.

        Args:
            initial_ready:
                Initial readiness state.
            dispatch_delay_sec:
                Artificial delay inserted during dispatch().
            default_success:
                Default dispatch result used unless overridden for the next call.
        """
        super().__init__()
        self._ready = bool(initial_ready)
        self._dispatch_delay_sec = max(0.0, float(dispatch_delay_sec))
        self._default_success = bool(default_success)
        self._next_success_override: Optional[bool] = None
        self._last_result: Optional[DispatchResult] = None

    def is_ready(self) -> bool:
        """
        Return whether the emulator is ready.
        """
        return self._ready

    def set_ready(self, is_ready: bool) -> None:
        """
        Update readiness and notify the registered listener if it changed.
        """
        is_ready = bool(is_ready)
        if self._ready == is_ready:
            return

        self._ready = is_ready
        self.notify_ready_changed(is_ready)

    def set_dispatch_delay(self, delay_sec: float) -> None:
        """
        Set the artificial provisioning delay.
        """
        self._dispatch_delay_sec = max(0.0, float(delay_sec))

    def set_default_success(self, success: bool) -> None:
        """
        Set the default success result used for future dispatches.
        """
        self._default_success = bool(success)

    def set_next_result(self, success: bool) -> None:
        """
        Override only the next dispatch result.
        """
        self._next_success_override = bool(success)

    def get_last_result(self) -> Optional[DispatchResult]:
        """
        Return the most recent dispatch result, if any.
        """
        return self._last_result

    def dispatch(self, payload: dict[str, Any]) -> DispatchResult:
        """
        Emulate provisioning with the supplied payload.

        The entire payload is traversed recursively so that every field is
        consumed by the emulator.

        Args:
            payload:
                Complete provisioning payload.

        Returns:
            DispatchResult describing the emulated result.

        Raises:
            RuntimeError:
                The dispatcher is not ready.
            TypeError:
                The payload is not a dictionary.
        """
        if not self._ready:
            raise RuntimeError("Emulator dispatcher is not ready.")

        if not isinstance(payload, dict):
            raise TypeError("Provision payload must be a dictionary.")

        Logger.write(
            LogLevel.PROGRESS,
            "[EMULATOR] Received payload JSON:\n"
            f"{self._format_payload_for_log(payload)}",
        )

        start_time = time.monotonic()
        stats = _PayloadStats()
        self._consume_value(payload, stats)

        if self._dispatch_delay_sec > 0.0:
            time.sleep(self._dispatch_delay_sec)

        success = self._resolve_dispatch_success()
        elapsed_ms = int((time.monotonic() - start_time) * 1000)

        if success:
            result = DispatchResult(
                success=True,
                message=(
                    "Emulator provisioning completed successfully. "
                    f"Processed {stats.key_count} keys."
                ),
                details={
                    "emulator": True,
                    "dict_count": stats.dict_count,
                    "list_count": stats.list_count,
                    "scalar_count": stats.scalar_count,
                    "key_count": stats.key_count,
                    "elapsed_ms": elapsed_ms,
                },
            )
        else:
            result = DispatchResult(
                success=False,
                message=(
                    "Emulator provisioning failed intentionally. "
                    f"Processed {stats.key_count} keys before completion."
                ),
                details={
                    "emulator": True,
                    "dict_count": stats.dict_count,
                    "list_count": stats.list_count,
                    "scalar_count": stats.scalar_count,
                    "key_count": stats.key_count,
                    "elapsed_ms": elapsed_ms,
                    "reason": "forced_failure",
                },
            )

        self._last_result = result
        return result

    def _format_payload_for_log(self, payload: dict[str, Any]) -> str:
        try:
            return json.dumps(
                payload,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
        except Exception:
            return repr(payload)

    def close(self) -> None:
        """
        Release emulator resources.

        No external resources are owned by this implementation.
        """
        return

    def _resolve_dispatch_success(self) -> bool:
        """
        Resolve the current dispatch result and consume the one-shot override.
        """
        if self._next_success_override is not None:
            success = self._next_success_override
            self._next_success_override = None
            return success
        return self._default_success

    def _consume_value(self, value: Any, stats: _PayloadStats) -> None:
        """
        Recursively consume the full payload structure.

        This method intentionally walks every key and value in the payload so
        that emulation does not silently ignore any field.
        """
        if isinstance(value, dict):
            stats.dict_count += 1
            for key, child in value.items():
                _ = str(key)
                stats.key_count += 1
                self._consume_value(child, stats)
            return

        if isinstance(value, list):
            stats.list_count += 1
            for item in value:
                self._consume_value(item, stats)
            return

        if isinstance(value, tuple):
            stats.list_count += 1
            for item in value:
                self._consume_value(item, stats)
            return

        stats.scalar_count += 1
        self._consume_scalar(value)

    def _consume_scalar(self, value: Any) -> None:
        """
        Consume one scalar value.

        The consumed value is normalized to a string representation so that
        different payload value types are all handled explicitly.
        """
        if value is None:
            _ = "null"
            return

        if isinstance(value, bool):
            _ = "true" if value else "false"
            return

        if isinstance(value, (int, float, str)):
            _ = str(value)
            return

        if isinstance(value, bytes):
            _ = value.hex()
            return

        _ = repr(value)
