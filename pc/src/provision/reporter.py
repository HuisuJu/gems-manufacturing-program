"""
Provision result reporter.

This module writes human-readable provisioning result files for later manual
inspection. Sensitive provisioning payload data must not be written to the
report output.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


class ProvisionReporterError(Exception):
    """
    Base exception for provision reporter failures.
    """


@dataclass(frozen=True, slots=True)
class ProvisionReportRecord:
    """
    Human-readable provisioning result record.

    Attributes:
        index:
            Runtime-local provider handle used for this provisioning attempt.
            This value may be None when provisioning failed before a provider
            handle was issued.
        success:
            Final provisioning result.
        message:
            Human-readable summary suitable for operators.
        dispatcher_name:
            Name of the dispatcher implementation used for the attempt.
        started_at:
            UTC timestamp when provisioning started.
        finished_at:
            UTC timestamp when provisioning finished.
        details:
            Optional non-sensitive diagnostic details.
    """

    index: Optional[int]
    success: bool
    message: str
    dispatcher_name: str
    started_at: str
    finished_at: str
    details: Optional[dict[str, Any]] = None


class ProvisionReporter:
    """
    Write provisioning result files into a target directory.

    Report files are intended for human inspection, especially when a
    provisioning attempt fails. The reporter must never persist the full
    provisioning payload because it may contain sensitive values.
    """

    DEFAULT_REPORT_DIR_NAME = "provision_reports"

    def __init__(self, report_dir: str | Path | None = None) -> None:
        """
        Initialize the reporter.

        Args:
            report_dir:
                Directory where report files will be written. If None, a default
                "provision_reports" directory under the current working
                directory is used.
        """
        if report_dir is None:
            self._report_dir = Path.cwd() / self.DEFAULT_REPORT_DIR_NAME
        else:
            self._report_dir = Path(report_dir).expanduser().resolve()

    def set_report_dir(self, report_dir: str | Path) -> None:
        """
        Set the target directory used for future report files.
        """
        self._report_dir = Path(report_dir).expanduser().resolve()

    def get_report_dir(self) -> Path:
        """
        Return the current target report directory.
        """
        return self._report_dir

    def write(self, record: ProvisionReportRecord) -> Path:
        """
        Write one provisioning result report file.

        Args:
            record:
                Finalized report record.

        Returns:
            Path to the written report file.

        Raises:
            ProvisionReporterError:
                The report file could not be written.
        """
        try:
            self._report_dir.mkdir(parents=True, exist_ok=True)
            file_path = self._build_report_file_path(record)
            content = self._build_report_document(record)

            with file_path.open("w", encoding="utf-8") as fp:
                json.dump(content, fp, indent=2, ensure_ascii=False, sort_keys=True)
                fp.write("\n")

            return file_path

        except Exception as exc:
            raise ProvisionReporterError(
                "Failed to write the provisioning result report file."
            ) from exc

    def _build_report_file_path(self, record: ProvisionReportRecord) -> Path:
        """
        Build the output file path for the given report record.
        """
        timestamp = self._build_file_timestamp()
        result_text = "success" if record.success else "fail"
        index_text = f"{record.index:06d}" if record.index is not None else "noindex"
        file_name = f"{timestamp}_{index_text}_{result_text}.json"
        return self._report_dir / file_name

    def _build_report_document(
        self,
        record: ProvisionReportRecord,
    ) -> dict[str, Any]:
        """
        Build the JSON document to be written.

        Only non-sensitive summary information is included.
        """
        document: dict[str, Any] = {
            "version": 1,
            "index": record.index,
            "result": "success" if record.success else "fail",
            "message": record.message,
            "dispatcher": record.dispatcher_name,
            "started_at": record.started_at,
            "finished_at": record.finished_at,
            "written_at": self._build_iso_utc_now(),
        }

        if record.details:
            document["details"] = record.details

        return document

    def _build_file_timestamp(self) -> str:
        """
        Build a compact UTC timestamp for file names.
        """
        return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    def _build_iso_utc_now(self) -> str:
        """
        Build an ISO-like UTC timestamp string.
        """
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")