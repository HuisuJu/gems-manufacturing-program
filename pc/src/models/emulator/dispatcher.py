"""Emulator dispatcher for local testing without a real device."""

from __future__ import annotations

import json

import time

from typing import Any, Optional

from logger import Logger, LogLevel

from provision.dispatcher import ProvisionDispatcher
from stream import Stream


class _PayloadStats:
    """Payload traversal counters."""

    def __init__(self) -> None:
        self.dict_count = 0
        self.list_count = 0
        self.scalar_count = 0
        self.key_count = 0


class EmulatorDispatcher(ProvisionDispatcher):
    """Provision dispatcher for local testing. Simulates delay and success/fail."""

    def __init__(
        self,
        stream: Stream | None = None,
        *,
        initial_ready: bool = True,
        dispatch_delay_sec: float = 1.0,
        default_success: bool = True,
    ) -> None:
        if stream is None:
            stream = Stream.get_delegate()
        if stream is None:
            raise RuntimeError("Emulator dispatcher requires a stream instance.")

        super().__init__(stream)
        self._ready = bool(initial_ready)
        self._dispatch_delay_sec = max(0.0, float(dispatch_delay_sec))
        self._default_success = bool(default_success)
        self._next_success_override: Optional[bool] = None
        self._last_result: Optional[bool] = None

    def is_ready(self) -> bool:
        """Return whether the emulator is ready."""
        return self._ready

    def set_ready(self, is_ready: bool) -> None:
        """Update readiness and notify listener if changed."""
        is_ready = bool(is_ready)
        if self._ready == is_ready:
            return

        self._ready = is_ready

    def set_dispatch_delay(self, delay_sec: float) -> None:
        """Set the artificial provisioning delay."""
        self._dispatch_delay_sec = max(0.0, float(delay_sec))

    def set_default_success(self, success: bool) -> None:
        """Set the default success result for future dispatches."""
        self._default_success = bool(success)

    def set_next_result(self, success: bool) -> None:
        """Override the next dispatch result once."""
        self._next_success_override = bool(success)

    def get_last_result(self) -> Optional[bool]:
        """Return the most recent dispatch result."""
        return self._last_result

    def dispatch(self, factory_data: dict[str, Any]) -> bool:
        """Emulate provisioning. Returns True on success, False on failure."""
        if not self._ready:
            raise RuntimeError("Emulator dispatcher is not ready.")

        if not isinstance(factory_data, dict):
            raise TypeError("Provision payload must be a dictionary.")

        Logger.write(
            LogLevel.DEBUG,
            "[EMULATOR] Received payload JSON:\n"
            f"{self._format_payload_for_log(factory_data)}",
        )

        payload_bytes = json.dumps(
            factory_data,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")

        if not self.stream.write(payload_bytes):
            Logger.write(LogLevel.WARNING, "Emulator stream write failed.")
            self._last_result = False
            return False

        # Non-blocking ACK poll to exercise the stream read path.
        _ = self.stream.read(size=1, timeout=0.0)

        start_time = time.monotonic()
        stats = _PayloadStats()
        self._consume_value(factory_data, stats)

        if self._dispatch_delay_sec > 0.0:
            time.sleep(self._dispatch_delay_sec)

        success = self._resolve_dispatch_success()
        elapsed_ms = int((time.monotonic() - start_time) * 1000)

        if success:
            Logger.write(
                LogLevel.DEBUG,
                "Emulator provisioning completed successfully. "
                f"dict={stats.dict_count}, list={stats.list_count}, "
                f"scalar={stats.scalar_count}, keys={stats.key_count}, "
                f"elapsed_ms={elapsed_ms}",
            )
        else:
            Logger.write(
                LogLevel.WARNING,
                "Emulator provisioning failed intentionally. "
                f"dict={stats.dict_count}, list={stats.list_count}, "
                f"scalar={stats.scalar_count}, keys={stats.key_count}, "
                f"elapsed_ms={elapsed_ms}",
            )

        self._last_result = success
        return success

    def _format_payload_for_log(self, payload: dict[str, Any]) -> str:
        """Convert payload to a formatted JSON string for logging."""
        payload_for_log = self._build_payload_for_log(payload)

        try:
            return json.dumps(
                payload_for_log,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
        except Exception:
            return repr(payload_for_log)

    def _build_payload_for_log(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Build a log-friendly payload with binary fields rendered as hex strings."""
        binary_encoded_fields = {
            "cd_cert",
            "dac_cert",
            "dac_private_key",
            "dac_public_key",
            "pai_cert",
            "spake2p_salt",
            "spake2p_verifier_w0",
            "spake2p_verifier_L",
        }

        converted: dict[str, Any] = {}
        for key, value in payload.items():
            if isinstance(value, bytes):
                converted[key] = value.hex().upper()
                continue

            if key == "spake2p_salt" and isinstance(value, list):
                try:
                    converted[key] = bytes(value).hex().upper()
                except Exception as exc:
                    Logger.write(
                        LogLevel.ALERT,
                        "에뮬레이터 로그 포맷 변환 중 오류가 발생했습니다. "
                        "해당 필드는 원본 값으로 표시됩니다. "
                        f"field={key} ({type(exc).__name__}: {exc})",
                    )
                    converted[key] = value
                continue

            if key in binary_encoded_fields and isinstance(value, str):
                try:
                    normalized = "".join(value.strip().split())
                    converted[key] = bytes.fromhex(normalized).hex().upper()
                except Exception as exc:
                    Logger.write(
                        LogLevel.ALERT,
                        "에뮬레이터 로그 포맷 변환 중 오류가 발생했습니다. "
                        "해당 필드는 원본 문자열로 표시됩니다. "
                        f"field={key} ({type(exc).__name__}: {exc})",
                    )
                    converted[key] = value
                continue

            converted[key] = value

        return converted

    def _resolve_dispatch_success(self) -> bool:
        """Resolve dispatch result and consume the one-shot override if set."""
        if self._next_success_override is not None:
            success = self._next_success_override
            self._next_success_override = None
            return success
        return self._default_success

    def _consume_value(self, value: Any, stats: _PayloadStats) -> None:
        """Recursively walk every key and value in the payload."""
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
        """Consume one scalar value by normalizing it to a string."""
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
