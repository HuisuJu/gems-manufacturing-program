from enum import Enum

MODEL_NAME_KEY = "model_name"
STATION_ID_KEY = "station_id"
REPORT_DIR_PATH_KEY = "report_file_path"
DAC_POOL_PATH_KEY = "dac_pool_path"
PAI_FILE_PATH_KEY = "pai_file_path"
CD_FILE_PATH_KEY = "cd_file_path"

class ModelName(str, Enum):
    """Supported models."""

    DOORLOCK   = "doorlock"
    THERMOSTAT = "thermostat"
    EMULATOR   = "emulator"
