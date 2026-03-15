"""Emulator model factory."""

from __future__ import annotations

from pathlib import Path

from factory_data.provider import FactoryDataProvider
from factory_data.schema import FactoryDataSchema
from logger import Logger, LogLevel
from provision.manager import ProvisionManager
from system import ModelName

from .dispatcher import EmulatorDispatcher
from .stream import EmulatorStream

_schema: FactoryDataSchema | None = None
_stream: EmulatorStream | None = None
_dispatcher: EmulatorDispatcher | None = None


def setup(
    schema_dir: Path,
    model: ModelName,
) -> None:
    """Create and store all runtime objects for emulator."""
    global _schema, _stream, _dispatcher

    _schema = FactoryDataSchema(
        base_schema_file=schema_dir / "base.schema.json",
        model_schema_file=schema_dir / f"{model.value}.schema.json",
    )

    if not FactoryDataProvider.is_initialized():
        FactoryDataProvider.init(_schema)

    _stream = EmulatorStream()
    _dispatcher = EmulatorDispatcher(stream=_stream)
    ProvisionManager.register_dispatcher(_dispatcher)
    ProvisionManager.activate()

    Logger.write(LogLevel.DEBUG, "Emulator runtime setup completed.")


def teardown() -> None:
    """Stop manager, close stream, then clear all references."""
    global _schema, _stream, _dispatcher

    ProvisionManager.stop()

    if _stream is not None:
        _stream.close()

    _schema = None
    _stream = None
    _dispatcher = None

    Logger.write(LogLevel.DEBUG, "Emulator runtime teardown completed.")
