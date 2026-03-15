from __future__ import annotations

from .retriever import Retriever
from .schema import FactoryDataSchema
from .retrievers import (
    DoorLockSerialNumberRetriever,
    ManufacturingDataRetriever,
    MatterAttestationDataRetriever,
    MatterOnboardingDataRetriever,
    ThermostatSerialNumberRetriever,
)
from system import ModelName


class FactoryDataRetrieverFactoryError(Exception):
    """Raised when a schema model does not have a retriever configuration."""


class FactoryDataRetrieverFactory:
    """Create retrievers for one schema."""

    @classmethod
    def create(cls, schema: FactoryDataSchema) -> list[Retriever]:
        """Create retrievers for the given schema."""
        _ = cls
        model = schema.get_model()

        if model == ModelName.DOORLOCK:
            return [
                DoorLockSerialNumberRetriever(),
                ManufacturingDataRetriever(),
                MatterAttestationDataRetriever(),
                MatterOnboardingDataRetriever(),
            ]

        if model == ModelName.THERMOSTAT:
            return [
                ThermostatSerialNumberRetriever(),
                MatterAttestationDataRetriever(),
                MatterOnboardingDataRetriever(),
            ]

        if model == ModelName.EMULATOR:
            return [
                ManufacturingDataRetriever(),
                MatterAttestationDataRetriever(),
                MatterOnboardingDataRetriever(),
            ]

        raise FactoryDataRetrieverFactoryError(
            f"No retriever configuration exists for model '{model.value}'."
        )
