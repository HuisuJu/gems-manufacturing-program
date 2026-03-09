"""
Retriever abstraction for replenishing factory data pool files.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol


class FactoryDataRetriever(Protocol):
    """
    Protocol for pool retrievers.

    A retriever is responsible for fetching additional JSON files into the
    configured pool directory.
    """

    def fetch(self, pool_path: Path, count: int) -> bool:
        """
        Fetch additional factory data JSON files into the target pool directory.

        Args:
            pool_path:
                Destination directory where fetched JSON files must be stored.
            count:
                Desired number of additional items to fetch.

        Returns:
            True if the fetch operation succeeded, otherwise False.
        """
        ...


class NullFactoryDataRetriever:
    """
    Default no-op retriever.

    This implementation intentionally does nothing and always reports failure.
    It is useful as a placeholder until a real retriever is configured.
    """

    def fetch(self, pool_path: Path, count: int) -> bool:
        """
        Placeholder retriever implementation.

        TODO:
            Implement retrieval from the actual source (for example, a local
            service endpoint or another provision data source).
        """
        _ = pool_path
        _ = count
        return False