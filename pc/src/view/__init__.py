from importlib import import_module

__all__ = ['Window', 'ProvisioningFrame', 'SettingFrame']

_EXPORT_MAP = {
    'Window': '.window',
    'ProvisioningFrame': '.frame',
    'SettingFrame': '.frame',
}


def __getattr__(name: str) -> object:
    module_name = _EXPORT_MAP.get(name)
    if module_name is None:
        raise AttributeError(f'module {__name__!r} has no attribute {name!r}')

    module = import_module(module_name, __name__)
    value = getattr(module, name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__))

