from gui import Window, ProvisioningPage, SettingPage


def main() -> None:
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