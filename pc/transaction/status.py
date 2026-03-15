from __future__ import annotations

from enum import IntEnum


class FactoryStatusCode(IntEnum):
    """Factory transaction status codes."""

    UNSPECIFIED = 0
    OK = 1
    INVALID_TRANSACTION = 2
    INVALID_ARGUMENT = 3
    INVALID_ITEM = 4
    INVALID_DATA = 5
    INTERNAL_ERROR = 6
    UNSUPPORTED = 7


class FactoryStatusError(Exception):
    """Raised when the device returns a non-OK status."""

    def __init__(self, status: FactoryStatusCode):
        self.status = status
        super().__init__(f"factory transaction failed with status: {status.name}")


def raise_for_status(status: FactoryStatusCode) -> None:
    """Raise FactoryStatusError if status is not OK."""
    if status != FactoryStatusCode.OK:
        raise FactoryStatusError(status)
