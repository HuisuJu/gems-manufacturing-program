import sys

from gui import Window, ProvisioningPage, SettingPage
from emulator.dispatcher import EmulatorDispatcher


def _is_emulator_mode(argv: list[str]) -> bool:
    """
    Return whether emulator mode was requested from command-line arguments.
    """
    return "--emulator" in argv or "-e" in argv


if __name__ == "__main__":
    emulator_mode = _is_emulator_mode(sys.argv[1:])

    window = Window(
        [
            (ProvisioningPage, "Provisioning"),
            (SettingPage, "Setting"),
        ]
    )

    if emulator_mode:
        try:
            provisioning_page = window.pages.get("Provisioning")
            if provisioning_page is not None:
                provisioning_page.set_provision_dispatcher(
                    EmulatorDispatcher(
                        initial_ready=True,
                        dispatch_delay_sec=1.0,
                        default_success=True,
                    )
                )
        except Exception:
            pass

    window.mainloop()