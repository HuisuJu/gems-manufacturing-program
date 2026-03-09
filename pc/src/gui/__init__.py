from importlib import import_module

__all__ = ['Window', 'ProvisioningFrame', 'SettingFrame']

_EXPORT_MAP = {
    'Window': 'gui.window',
    'ProvisioningFrame': 'gui.provisioning_frame',
    'SettingFrame': 'gui.setting_frame',
}


def __getattr__(name: str):
    module_name = _EXPORT_MAP.get(name)
    if module_name is None:
        raise AttributeError(f'module {__name__!r} has no attribute {name!r}')

    module = import_module(module_name)
    value = getattr(module, name)
    globals()[name] = value
    return value

