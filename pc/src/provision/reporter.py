"""
Provision result reporter.

This module writes provisioning result files and keeps the full injected
factory data payload in the report output for now.
"""

from __future__ import annotations

import base64

import json

from datetime import datetime, timezone

from pathlib import Path

from typing import Any, NamedTuple, Optional

from logger import Logger, LogLevel


class ProvisionReporterError(Exception):
    """
    Base exception for provision reporter failures.
    """


class ProvisionReportRecord(NamedTuple):
    """
    Provisioning result record.

    Attributes:
        index:
            Runtime-local provisioning handle or identifier.
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
        injected_data:
            Full factory data payload used for the provisioning attempt.
        details:
            Optional diagnostic details.
    """

    index: Optional[int]
    success: bool
    message: str
    dispatcher_name: str
    started_at: str
    finished_at: str
    injected_data: dict[str, Any]
    details: Optional[dict[str, Any]] = None


class ProvisionReporter:
    """
    Write provisioning result files into a target directory.
    """

    DEFAULT_REPORT_DIR_NAME = "report"

    def __init__(self) -> None:
        """
        Initialize the reporter.
        """
        self._report_dir = self._build_default_report_dir()

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

    def _build_default_report_dir(self) -> Path:
        """
        Build the default report directory.

        The default location is a "report" directory under the current working
        directory, which is expected to be the program root directory.
        """
        return Path.cwd() / self.DEFAULT_REPORT_DIR_NAME

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
            "injected_data": self._build_injected_data_document(
                record.injected_data
            ),
        }

        if record.details:
            document["details"] = record.details

        return document

    def _build_injected_data_document(
        self,
        injected_data: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Build report-friendly injected_data.

        Binary fields are rendered as uppercase contiguous hex strings.
        """
        binary_base64_fields = {
            "certification_declaration",
            "dac_cert",
            "dac_private_key",
            "dac_public_key",
            "pai_cert",
            "spake2p_salt",
            "spake2p_verifier",
        }

        converted: dict[str, Any] = {}
        for key, value in injected_data.items():
            if isinstance(value, bytes):
                converted[key] = value.hex().upper()
                continue

            if key in binary_base64_fields and isinstance(value, str):
                try:
                    converted[key] = base64.b64decode(
                        value,
                        validate=True,
                    ).hex().upper()
                except Exception as exc:
                    Logger.write(
                        LogLevel.ALERT,
                        "리포트 injected_data 변환 중 오류가 발생했습니다. "
                        "해당 필드는 원본 문자열로 저장됩니다. "
                        f"field={key} ({type(exc).__name__}: {exc})",
                    )
                    converted[key] = value
                continue

            converted[key] = value

        return converted

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
