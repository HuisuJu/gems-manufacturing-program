"""Public logging package API.

This package exposes in-memory logging, presentation, and save helpers used by
the PC tooling.

Exports:
    Logger: Thread-safe in-memory logger.
    LogLevel: Log severity enum.
    LogRecord: Single log record data model.
    LogSaver: Facade for saving logs through presenter types.
    LogPresenterType: Available presenter/output format types.
    LogPresenter: Abstract presenter interface.
    LogTextPresenter: Plain-text presenter implementation.
"""

from .manager import Logger, LogLevel, LogRecord

from .saver import LogSaver

from .presenter import LogPresenterType, LogPresenter, LogTextPresenter

__all__ = [
    "Logger",
    "LogLevel",
    "LogRecord",
    "LogSaver",
    "LogPresenterType",
    "LogPresenter",
    "LogTextPresenter",
]
