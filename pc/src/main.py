from __future__ import annotations

import sys

from pathlib import Path

from logger import Logger, LogLevel

from system import MODEL_NAME_KEY, ModelName, Settings

_active_model: ModelName | None = None


class ApplicationInitializationError(Exception):
    """Raised when application-level initialization fails."""


def _get_schema_dir() -> Path:
    """Return the schema/json directory for source and bundled execution."""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        schema_dir = Path(sys._MEIPASS) / "schema" / "json"
    else:
        # Source execution:
        # repo_root/
        #   schema/json
        #   pc/src/main.py
        schema_dir = Path(__file__).resolve().parents[2] / "schema" / "json"

    if not schema_dir.is_dir():
        raise ApplicationInitializationError(
            f"Schema directory not found: {schema_dir}"
        )

    return schema_dir


def _normalize_model_name(value: object) -> ModelName:
    """Convert one raw value to ModelName."""
    if isinstance(value, ModelName):
        return value

    if isinstance(value, str) and value:
        try:
            return ModelName(value)
        except ValueError as exc:
            raise ApplicationInitializationError(
                f"Invalid model value: {value!r}"
            ) from exc

    raise ApplicationInitializationError(
        f"Invalid model value: {value!r}"
    )


def _teardown_active_model() -> None:
    """Teardown the currently active model's runtime, if any."""
    global _active_model

    if _active_model is None:
        return

    match _active_model:
        case ModelName.DOORLOCK:
            from models import doorlock
            doorlock.teardown()
        case ModelName.THERMOSTAT:
            from models import thermostat
            thermostat.teardown()
        case ModelName.EMULATOR:
            from models import emulator
            emulator.teardown()

    _active_model = None


def _setup_runtime_for_model(model: ModelName) -> None:
    """Teardown the previous model and set up a new one."""
    global _active_model

    _teardown_active_model()
    schema_dir = _get_schema_dir()

    match model:
        case ModelName.DOORLOCK:
            from models import doorlock
            doorlock.setup(schema_dir, model)

        case ModelName.THERMOSTAT:
            from models import thermostat
            thermostat.setup(schema_dir, model)

        case ModelName.EMULATOR:
            from models import emulator
            emulator.setup(schema_dir, model)

        case _:
            raise ApplicationInitializationError(
                f"Unsupported model: {model!r}"
            )

    _active_model = model


def _run_application() -> None:
    """Initialize and run the application."""

    def on_model_selected(_: str, value: object) -> None:
        """Reconfigure runtime objects when model changes."""
        model = _normalize_model_name(value)
        _setup_runtime_for_model(model)

    Settings.subscribe(MODEL_NAME_KEY, on_model_selected)

    existing_model = Settings.get(MODEL_NAME_KEY)
    if existing_model is not None:
        on_model_selected(MODEL_NAME_KEY, existing_model)
    else:
        Logger.write(
            LogLevel.DEBUG,
            "MODEL_NAME is not set yet. Runtime setup is deferred.",
        )

    from view import Window

    window = Window()
    window.mainloop()


def main() -> None:
    """Application entry point."""
    Logger.start()
    Settings.init()

    try:
        Logger.write(LogLevel.DEBUG, "Application start.")
        _run_application()

    except Exception as exc:
        Logger.write(
            LogLevel.ALERT,
            "Unhandled exception in application main loop. "
            f"({type(exc).__name__}: {exc})",
        )
        raise

    finally:
        _teardown_active_model()
        Logger.write(LogLevel.DEBUG, "Application shutdown.")
        Logger.stop(timeout_sec=1.0)


if __name__ == "__main__":
    main()
