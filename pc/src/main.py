from __future__ import annotations

from pathlib import Path

from typing import Any, cast

from logger import Logger, LogLevel

from settings import ModelName, SettingsItem, settings as app_settings

from stream import SerialStream, Stream

from emulator import EmulatorDispatcher, EmulatorStream

from thermostat import ThermostatDispatcher

from factory_data import FactoryDataProvider

from factory_data.retriever import (
    DeviceIdentityRetriever,
    ManufacturingDataRetriever,
    MatterAttestationDataRetriever,
    MatterOnboardingDataRetriever,
)

from matter.attestation_store import CdStore, DacCredentialPoolStore, PaiCertStore

from provision import ProvisionManager, ProvisionReporter

from gui.window import Window

from gui.provisioning_frame import ProvisioningFrame

from gui.setting_frame import SettingFrame


def _build_provider_for_model(model_name: ModelName) -> FactoryDataProvider:
    """
    Build the factory data provider for the selected model.

    This function is intentionally small here, because the exact provider
    wiring depends on the current retriever/schema configuration.
    """
    schema_directory = Path(__file__).resolve().parents[2] / "schema"

    provider = FactoryDataProvider(
        schema_directory=schema_directory,
        model_name=model_name.value,
    )

    provider.add_retriever(DeviceIdentityRetriever())
    provider.add_retriever(ManufacturingDataRetriever())
    provider.add_retriever(
        MatterAttestationDataRetriever(
            dac_store=DacCredentialPoolStore(),
            pai_store=PaiCertStore(),
            cd_store=CdStore(),
        )
    )
    provider.add_retriever(MatterOnboardingDataRetriever())

    return provider


def _is_provider_prerequisite_ready() -> bool:
    """
    Return whether provider prerequisites are configured.

    START must remain disabled until all attestation input paths are set.
    """
    required_items = (
        SettingsItem.DAC_POOL_DIR_PATH,
        SettingsItem.PAI_FILE_PATH,
        SettingsItem.CD_FILE_PATH,
    )

    return all(app_settings.get(item) is not None for item in required_items)


def _build_dispatcher_for_model(
    model_name: ModelName,
    serial_manager: Stream,
):
    """
    Build the dispatcher for the selected model.

    Emulator and Thermostat are supported directly.
    """
    if model_name == ModelName.EMULATOR:
        return EmulatorDispatcher(
            initial_ready=True,
            dispatch_delay_sec=1.0,
            default_success=True,
        )

    if model_name == ModelName.THERMOSTAT:
        return ThermostatDispatcher(stream=serial_manager)

    raise NotImplementedError(
        f"Dispatcher for model '{model_name.value}' is not implemented yet."
    )


def _wire_provisioning(
    window: Window,
    serial_manager: Stream,
) -> None:
    """
    Wire runtime objects after the window and pages have been created.
    """
    provisioning_frame = window.pages.get("Provisioning")
    if provisioning_frame is None:
        Logger.write(LogLevel.WARNING, "Provisioning page is missing.")
        return

    if not isinstance(provisioning_frame, ProvisioningFrame):
        Logger.write(LogLevel.WARNING, "Provisioning page type is invalid.")
        return

    model_name = cast(ModelName | None, app_settings.get(SettingsItem.MODEL_NAME))
    if model_name is None:
        Logger.write(LogLevel.WARNING, "Model name is not configured.")
        return

    try:
        provider = _build_provider_for_model(model_name)
        dispatcher = _build_dispatcher_for_model(
            model_name=model_name,
            serial_manager=serial_manager,
        )
        reporter = cast(Any, ProvisionReporter)()

        provision_manager = cast(Any, ProvisionManager)(
            provider=provider,
            dispatcher=dispatcher,
            view=provisioning_frame.provisioning_view,
            reporter=reporter,
            provider_ready_checker=_is_provider_prerequisite_ready,
        )
    except Exception as exc:
        Logger.write(
            LogLevel.WARNING,
            "Failed to initialize provisioning runtime "
            f"({type(exc).__name__}: {exc})",
        )
        return

    def on_provisioning_user_event(event) -> None:
        if event.action == "start":
            provision_manager.start()
            return

        if event.action == "finish":
            provision_manager.finish()
            provisioning_frame.log_settings_view.handle_finish()
            return

        Logger.write(
            LogLevel.WARNING,
            f"Unhandled provisioning user action: {event.action}",
        )

    provisioning_frame.provisioning_view.set_user_event_listener(
        on_provisioning_user_event
    )

    provision_manager.activate()


def _select_serial_manager_for_model(
    model_name: ModelName | None,
    serial_manager: SerialStream,
    emulator_serial_manager: EmulatorStream,
) -> Stream:
    if model_name == ModelName.EMULATOR:
        return emulator_serial_manager
    return serial_manager


def main() -> None:
    Logger.start()

    try:
        serial_manager = SerialStream()
        emulator_serial_manager = EmulatorStream()

        def _create_provisioning_frame(master):
            selected_serial_manager = _select_serial_manager_for_model(
                cast(ModelName | None, app_settings.get(SettingsItem.MODEL_NAME)),
                serial_manager,
                emulator_serial_manager,
            )

            return ProvisioningFrame(
                master,
                serial_manager=cast(SerialStream, selected_serial_manager),
            )

        page_factories = [
            (_create_provisioning_frame, "Provisioning"),
            (SettingFrame, "Setting"),
        ]

        window = Window(page_factories)

        if window.selected_model_name is None:
            return

        selected_serial_manager = _select_serial_manager_for_model(
            window.selected_model_name,
            serial_manager,
            emulator_serial_manager,
        )

        _wire_provisioning(
            window=window,
            serial_manager=selected_serial_manager,
        )

        window.mainloop()

    finally:
        Logger.stop()


if __name__ == "__main__":
    main()