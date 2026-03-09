from gui import Window, ProvisioningFrame, SettingFrame


def main() -> None:
    """
    Entry point of the factory provisioning tool.
    """
    window = Window(
        [
            (ProvisioningFrame, "Provisioning"),
            (SettingFrame, "Setting"),
        ]
    )

    if window.winfo_exists():
        window.mainloop()


if __name__ == "__main__":
    main()
