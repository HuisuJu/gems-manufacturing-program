from __future__ import annotations

from .schema import FactoryDataSchema

from .retriever import Retriever

from .retrievers.device_identity import DeviceIdentityRetriever

from .retrievers.manufacturing import ManufacturingDataRetriever

from .retrievers.matter_attestation import MatterAttestationDataRetriever

from .retrievers.matter_onboarding import MatterOnboardingDataRetriever


class FactoryDataRetrieverFactory:
    """Create retrievers for one schema."""

    @classmethod
    
    def create(cls, schema: FactoryDataSchema) -> list[Retriever]:
        """Create retrievers for the given schema."""
        retrievers: list[Retriever] = [
            DeviceIdentityRetriever(),
            ManufacturingDataRetriever(),
            MatterAttestationDataRetriever(),
            MatterOnboardingDataRetriever(),
        ]

        return retrievers
