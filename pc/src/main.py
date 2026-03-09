from gui import Window, ProvisioningPage, SettingPage


def main() -> None:
    """
    Entry point of the factory provisioning tool.
    """
    window = Window(
        [
            (ProvisioningPage, "Provisioning"),
            (SettingPage, "Setting"),
        ]
    )

    if window.winfo_exists():
        window.mainloop()


if __name__ == "__main__":
    main()