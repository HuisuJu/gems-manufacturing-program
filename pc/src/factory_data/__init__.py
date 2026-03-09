"""
Factory data provisioning package.

This package provides the public interface used by the provisioning workflow
to obtain and report factory data items.

Typical usage:

    from factory_data import FactoryDataProvider

    provider = FactoryDataProvider()

    result = provider.get()
    data = result.data

    # perform provisioning

    provider.report(result.index, success=True)
"""

from .provider import (
    FactoryDataProvider,
    FactoryDataGetResult,
    FactoryDataProviderError,
    FactoryDataProviderInProgressError,
    FactoryDataProviderHandleError,
)

__all__ = [
    "FactoryDataProvider",
    "FactoryDataGetResult",
    "FactoryDataProviderError",
    "FactoryDataProviderInProgressError",
    "FactoryDataProviderHandleError",
]