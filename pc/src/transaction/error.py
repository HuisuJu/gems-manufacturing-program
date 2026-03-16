from __future__ import annotations


class ProvisionError(Exception):
    """Base exception for provisioning failures."""


class ProvisionValidationError(ProvisionError):
    """Raised when input provisioning data is invalid."""


class ProvisionTransportError(ProvisionError):
    """Raised when transport/session/frame communication fails."""


class ProvisionProtocolError(ProvisionError):
    """Raised when the remote protocol response is invalid or unexpected."""


class ProvisionExecutionError(ProvisionError):
    """Raised when the provisioning transaction fails."""
