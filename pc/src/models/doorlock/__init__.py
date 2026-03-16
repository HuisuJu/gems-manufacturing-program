"""Doorlock model factory."""

from __future__ import annotations

_schema = None
_stream = None
_dispatcher = None


def setup(
	schema_dir,
	model,
) -> None:
	"""Create and store runtime objects for doorlock."""
	global _schema, _stream, _dispatcher

	factory_data_provider_module = __import__(
		'factory_data.provider',
		fromlist=['FactoryDataProvider'],
	)
	factory_data_schema_module = __import__(
		'factory_data.schema',
		fromlist=['FactoryDataSchema'],
	)
	logger_module = __import__('logger', fromlist=['Logger', 'LogLevel'])
	provision_manager_module = __import__(
		'provision.manager',
		fromlist=['ProvisionManager'],
	)
	serial_stream_module = __import__('stream.serial', fromlist=['SerialStream'])
	transaction_dispatcher_module = __import__(
		'transaction.dispatcher',
		fromlist=['GenericProvisionDispatcher'],
	)

	FactoryDataProvider = factory_data_provider_module.FactoryDataProvider
	FactoryDataSchema = factory_data_schema_module.FactoryDataSchema
	Logger = logger_module.Logger
	LogLevel = logger_module.LogLevel
	ProvisionManager = provision_manager_module.ProvisionManager
	SerialStream = serial_stream_module.SerialStream
	GenericProvisionDispatcher = (
		transaction_dispatcher_module.GenericProvisionDispatcher
	)

	_schema = FactoryDataSchema(
		base_schema_file=schema_dir / 'base.schema.json',
		model_schema_file=schema_dir / f'{model.value}.schema.json',
	)

	if not FactoryDataProvider.is_initialized():
		FactoryDataProvider.init(_schema)

	_stream = SerialStream()
	_dispatcher = GenericProvisionDispatcher(stream=_stream)
	ProvisionManager.register_dispatcher(_dispatcher)
	ProvisionManager.activate()

	Logger.write(LogLevel.DEBUG, 'Doorlock runtime setup completed.')


def teardown() -> None:
	"""Stop manager, release dispatcher and stream, then clear all references."""
	global _schema, _stream, _dispatcher

	logger_module = __import__('logger', fromlist=['Logger', 'LogLevel'])
	provision_manager_module = __import__(
		'provision.manager',
		fromlist=['ProvisionManager'],
	)

	Logger = logger_module.Logger
	LogLevel = logger_module.LogLevel
	ProvisionManager = provision_manager_module.ProvisionManager

	ProvisionManager.stop()

	if _stream is not None:
		_stream.close()

	_schema = None
	_stream = None
	_dispatcher = None

	Logger.write(LogLevel.DEBUG, 'Doorlock runtime teardown completed.')
