"""Provisioning subsystem public API."""

from importlib import import_module

__all__ = [
    "ProvisionManager",
    "ProvisionManagerError",
    "ProvisionDispatcher",
    "DispatchResult",
    "ProvisionReporter",
    "ProvisionReporterError",
    "ProvisionReportRecord",
]

_EXPORT_MAP = {
    "ProvisionManager": ".manager",
    "ProvisionManagerError": ".manager",
    "ProvisionDispatcher": ".dispatcher",
    "DispatchResult": ".dispatcher",
    "ProvisionReporter": ".reporter",
    "ProvisionReporterError": ".reporter",
    "ProvisionReportRecord": ".reporter",
}


def __getattr__(name: str) -> object:
    module_name = _EXPORT_MAP.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

    module = import_module(module_name, __name__)
    value = getattr(module, name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__))
