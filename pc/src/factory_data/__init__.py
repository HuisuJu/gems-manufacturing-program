"""
Factory data package public API.

This package provides:
    - FactoryDataProvider for provisioning-time payload retrieval/reporting
    - FactoryDataPoolManager for pool path management and pool status handling
"""

from .provider import (
    FactoryDataProvider,
    FactoryDataGetResult,
    FactoryDataProviderError,
    FactoryDataProviderInProgressError,
    FactoryDataProviderHandleError,
)

from .pool_manager import (
    FactoryDataPoolManager,
    FactoryDataPoolManagerError,
    FactoryDataPoolInactiveError,
    FactoryDataPoolPathError,
    FactoryDataPoolLeaseError,
    FactoryDataPoolEmptyError,
    FactoryDataPoolReport,
    FactoryDataPoolLease,
)

__all__ = [
    # provider
    "FactoryDataProvider",
    "FactoryDataGetResult",
    "FactoryDataProviderError",
    "FactoryDataProviderInProgressError",
    "FactoryDataProviderHandleError",
    # pool manager
    "FactoryDataPoolManager",
    "FactoryDataPoolManagerError",
    "FactoryDataPoolInactiveError",
    "FactoryDataPoolPathError",
    "FactoryDataPoolLeaseError",
    "FactoryDataPoolEmptyError",
    "FactoryDataPoolReport",
    "FactoryDataPoolLease",
]