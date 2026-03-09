from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Sequence

from .manager import LogRecord
from .presenter import LogPresenter, LogPresenterType, LogTextPresenter


class LogSaver:
    """
    Dispatches log save requests to the appropriate presenter.

    The saver owns presenter instances, creates the output file, and
    delegates the actual content writing to the selected presenter.
    """

    _presenters: dict[LogPresenterType, LogPresenter] = {
        LogPresenterType.TEXT: LogTextPresenter(),
    }

    @classmethod
    def save(
        cls,
        records: Sequence[LogRecord],
        path: str | Path,
        presenter_type: LogPresenterType,
    ) -> Path:
        """
        Saves the provided records using the selected presenter type.

        A timestamp suffix is always appended to the output filename.
        If the target file already exists, it is overwritten.

        Args:
            records:
                Records to store.
            path:
                Base destination file path.
            presenter_type:
                Presenter type used to determine the output format.

        Returns:
            The final output path actually used for saving.

        Raises:
            ValueError:
                Raised when the presenter type is not supported.
        """
        presenter = cls._presenters.get(presenter_type)
        if presenter is None:
            raise ValueError(f"Unsupported presenter type: {presenter_type}")

        output_path = cls._build_output_path(path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with output_path.open("w", encoding="utf-8") as file:
            presenter.save(
                records=records,
                file=file,
            )

        return output_path

    @classmethod
    def _build_output_path(cls, path: str | Path) -> Path:
        """
        Builds the final output path with an appended timestamp suffix.

        Args:
            path:
                Base file path requested by the caller.

        Returns:
            A normalized Path object with a timestamped filename.
        """
        output_path = Path(path).expanduser()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        return output_path.with_name(
            f"{output_path.stem}_{timestamp}{output_path.suffix}"
        )