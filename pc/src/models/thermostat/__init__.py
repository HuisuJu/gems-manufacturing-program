"""Thermostat model factory."""

from __future__ import annotations

from pathlib import Path

from factory_data.provider import FactoryDataProvider
from factory_data.schema import FactoryDataSchema
from logger import Logger, LogLevel
from provision.manager import ProvisionManager
from stream.serial import SerialStream
from .dispatcher import ThermostatDispatcher
from system import ModelName

_schema: FactoryDataSchema | None = None
_stream: SerialStream | None = None
_dispatcher: ThermostatDispatcher | None = None


def setup(
    schema_dir: Path,
    model: ModelName,
) -> None:
    """Create and store runtime objects for thermostat."""
    global _schema, _stream, _dispatcher

    _schema = FactoryDataSchema(
        base_schema_file=schema_dir / "base.schema.json",
        model_schema_file=schema_dir / f"{model.value}.schema.json",
    )

    if not FactoryDataProvider.is_initialized():
        FactoryDataProvider.init(_schema)

    _stream = SerialStream()
    _dispatcher = ThermostatDispatcher(stream=_stream)
    ProvisionManager.register_dispatcher(_dispatcher)
    ProvisionManager.activate()

    Logger.write(LogLevel.DEBUG, "Thermostat runtime setup completed.")


def teardown() -> None:
    """Stop manager, release dispatcher and stream, then clear all references."""
    global _schema, _stream, _dispatcher

    ProvisionManager.stop()

    if _dispatcher is not None:
        _dispatcher.destroy()

    if _stream is not None:
        _stream.close()

    _schema = None
    _stream = None
    _dispatcher = None

    Logger.write(LogLevel.DEBUG, "Thermostat runtime teardown completed.")
