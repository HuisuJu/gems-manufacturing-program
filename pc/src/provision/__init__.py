"""
Provisioning subsystem public API.

This package provides the provisioning workflow orchestration used by the
factory provisioning tool. The main entry point for external modules is
ProvisionManager.

Modules:
    dispatcher  - dispatcher interface used to send payloads to a device
    manager     - provisioning workflow state machine
    reporter    - provisioning result report writer
"""

from .manager import (
    ProvisionManager,
    ProvisionManagerEvent,
    ProvisionUIState,
)

from .dispatcher import (
    ProvisionDispatcher,
    DispatchResult,
)

from .reporter import (
    ProvisionReporter,
    ProvisionReportRecord,
)

__all__ = [
    # manager
    "ProvisionManager",
    "ProvisionManagerEvent",
    "ProvisionUIState",
    # dispatcher
    "ProvisionDispatcher",
    "DispatchResult",
    # reporter
    "ProvisionReporter",
    "ProvisionReportRecord",
]