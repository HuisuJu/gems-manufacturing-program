import json

import pytest

from pathlib import Path

from tempfile import TemporaryDirectory

from src.system.settings import (
    ModelName,
    Settings,
    SettingsItem,
    SettingsSerializationError,
)


class TestSettings:
    """Test Settings module."""

    def setup_method(self):
        """Reset Settings state before each test."""
        Settings._values.clear()
        Settings._subscribers.clear()
        Settings._initialized = False

    def test_init_creates_empty_values(self):
        """Test init creates empty values for all items."""
        Settings.init()
        assert Settings._initialized is True
        assert SettingsItem.MODEL_NAME in Settings._values
        assert SettingsItem.DAC_POOL_DIR_PATH in Settings._values
        assert SettingsItem.PAI_FILE_PATH in Settings._values
        assert SettingsItem.CD_FILE_PATH in Settings._values

    def test_get_returns_none_when_not_initialized(self):
        """Test get returns None when not initialized."""
        result = Settings.get(SettingsItem.MODEL_NAME)
        assert result is None

    def test_set_before_init_does_nothing(self):
        """Test set does nothing when not initialized."""
        Settings.set(SettingsItem.MODEL_NAME, ModelName.DOORLOCK)
        assert Settings.get(SettingsItem.MODEL_NAME) is None

    def test_set_and_get_value(self):
        """Test set and get values correctly."""
        Settings.init()
        Settings.set(SettingsItem.MODEL_NAME, ModelName.DOORLOCK)
        assert Settings.get(SettingsItem.MODEL_NAME) == ModelName.DOORLOCK

    def test_set_invalid_item_raises_error(self):
        """Test set with invalid item raises error."""
        Settings.init()
        with pytest.raises(KeyError):
            Settings.set('invalid-item', 'value')

    def test_set_same_value_does_not_save(self):
        """Test set with same value doesn't trigger save."""
        Settings.init()
        Settings.set(SettingsItem.MODEL_NAME, ModelName.DOORLOCK)
        # Clear _save to track if it's called again
        original_save = Settings._save
        save_called = False

        def mock_save():
            nonlocal save_called
            save_called = True
            original_save()

        Settings._save = mock_save
        Settings.set(SettingsItem.MODEL_NAME, ModelName.DOORLOCK)
        assert save_called is False
        Settings._save = original_save

    def test_clear_value(self):
        """Test clear sets value to None."""
        Settings.init()
        Settings.set(SettingsItem.MODEL_NAME, ModelName.DOORLOCK)
        Settings.clear(SettingsItem.MODEL_NAME)
        assert Settings.get(SettingsItem.MODEL_NAME) is None

    def test_subscribe_callback(self):
        """Test subscribe registers callback."""
        Settings.init()
        callback_called = False
        called_item = None
        called_value = None

        def test_callback(item, value):
            nonlocal callback_called, called_item, called_value
            callback_called = True
            called_item = item
            called_value = value

        Settings.subscribe(SettingsItem.MODEL_NAME, test_callback)
        Settings.set(SettingsItem.MODEL_NAME, ModelName.DOORLOCK)

        assert callback_called is True
        assert called_item == SettingsItem.MODEL_NAME
        assert called_value == ModelName.DOORLOCK

    def test_unsubscribe_callback(self):
        """Test unsubscribe removes callback."""
        Settings.init()
        callback_called = False

        def test_callback(item, value):
            nonlocal callback_called
            callback_called = True

        Settings.subscribe(SettingsItem.MODEL_NAME, test_callback)
        Settings.unsubscribe(SettingsItem.MODEL_NAME, test_callback)
        Settings.set(SettingsItem.MODEL_NAME, ModelName.DOORLOCK)

        assert callback_called is False

    def test_save_creates_file(self):
        """Test _save creates settings file."""
        with TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            Settings._SETTINGS_FILE_PATH = tmppath / 'settings.json'

            Settings.init()
            Settings.set(SettingsItem.MODEL_NAME, ModelName.DOORLOCK)

            assert Settings._SETTINGS_FILE_PATH.exists()

    def test_save_file_format(self):
        """Test _save writes correct JSON format."""
        with TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            Settings._SETTINGS_FILE_PATH = tmppath / 'settings.json'

            Settings.init()
            Settings.set(SettingsItem.MODEL_NAME, ModelName.DOORLOCK)

            with Settings._SETTINGS_FILE_PATH.open('r') as f:
                data = json.load(f)

            assert data['model-name'] == 'doorlock'

    def test_load_modelname_value(self):
        """Test _load correctly loads ModelName values."""
        with TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            Settings._SETTINGS_FILE_PATH = tmppath / 'settings.json'

            # Write test data
            test_data = {'model-name': 'thermostat'}
            with Settings._SETTINGS_FILE_PATH.open('w') as f:
                json.dump(test_data, f)

            Settings.init()
            assert Settings.get(SettingsItem.MODEL_NAME) == ModelName.THERMOSTAT

    def test_load_path_value(self):
        """Test _load correctly loads Path values."""
        with TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            Settings._SETTINGS_FILE_PATH = tmppath / 'settings.json'
            test_path = str(Path.home() / 'test')

            # Write test data
            test_data = {'dac-pool-dir-path': test_path}
            with Settings._SETTINGS_FILE_PATH.open('w') as f:
                json.dump(test_data, f)

            Settings.init()
            loaded_value = Settings.get(SettingsItem.DAC_POOL_DIR_PATH)
            assert isinstance(loaded_value, Path)
            assert loaded_value.is_absolute()

    def test_load_invalid_modelname(self):
        """Test _load handles invalid ModelName gracefully."""
        with TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            Settings._SETTINGS_FILE_PATH = tmppath / 'settings.json'

            # Write invalid ModelName
            test_data = {'model-name': 'invalid-model'}
            with Settings._SETTINGS_FILE_PATH.open('w') as f:
                json.dump(test_data, f)

            Settings.init()
            assert Settings.get(SettingsItem.MODEL_NAME) is None

    def test_load_nonexistent_file(self):
        """Test _load returns gracefully when file doesn't exist."""
        with TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            Settings._SETTINGS_FILE_PATH = tmppath / 'nonexistent.json'

            Settings.init()
            assert Settings.get(SettingsItem.MODEL_NAME) is None

    def test_load_invalid_json(self):
        """Test init raises when settings JSON is invalid."""
        with TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            Settings._SETTINGS_FILE_PATH = tmppath / 'settings.json'

            # Write invalid JSON
            with Settings._SETTINGS_FILE_PATH.open('w') as f:
                f.write('invalid json content')

            with pytest.raises(SettingsSerializationError):
                Settings.init()

    def test_load_non_dict_json(self):
        """Test init raises when settings JSON root is not an object."""
        with TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            Settings._SETTINGS_FILE_PATH = tmppath / 'settings.json'

            # Write list instead of dict
            with Settings._SETTINGS_FILE_PATH.open('w') as f:
                json.dump(['item1', 'item2'], f)

            with pytest.raises(SettingsSerializationError):
                Settings.init()

    def test_path_normalization(self):
        """Test Path values are normalized."""
        with TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            Settings._SETTINGS_FILE_PATH = tmppath / 'settings.json'

            # Write path with ~ and trailing slash
            test_data = {'dac-pool-dir-path': '~/test/path/'}
            with Settings._SETTINGS_FILE_PATH.open('w') as f:
                json.dump(test_data, f)

            Settings.init()
            loaded_value = Settings.get(SettingsItem.DAC_POOL_DIR_PATH)
            assert isinstance(loaded_value, Path)
            assert not str(loaded_value).startswith('~')
            assert loaded_value.is_absolute()

    def test_roundtrip_save_load(self):
        """Test values survive save and load cycle."""
        with TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            Settings._SETTINGS_FILE_PATH = tmppath / 'settings.json'

            Settings.init()
            test_path = Path.home() / 'data'
            Settings.set(SettingsItem.MODEL_NAME, ModelName.THERMOSTAT)
            Settings.set(SettingsItem.DAC_POOL_DIR_PATH, test_path)

            # Reset and reload
            Settings._values.clear()
            Settings._subscribers.clear()
            Settings._initialized = False
            Settings.init()

            assert Settings.get(SettingsItem.MODEL_NAME) == ModelName.THERMOSTAT
            assert Settings.get(SettingsItem.DAC_POOL_DIR_PATH) == test_path
