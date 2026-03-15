"""Provision result reporter."""

from __future__ import annotations

import copy
import json

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from factory_data.schema import FactoryDataSchema, FactoryDataSchemaFieldError
from system import REPORT_DIR_PATH_KEY, Settings


_STATS_FILE_NAME = "provision_stats.json"


@dataclass(frozen=True)
class ProvisionStats:
    """Accumulated provisioning statistics."""

    success_count: int
    error_count: int
    total_count: int


class ProvisionReporterError(Exception):
    """Base reporter error."""


class ProvisionReporterSerializationError(ProvisionReporterError):
    """Raised when report content cannot be converted into JSON-safe data."""


class ProvisionReporter:
    """Write provisioning result files and accumulated statistics to disk."""

    @classmethod
    def get_report_dir(cls) -> Path:
        """Return report directory configured in Settings."""
        return cls._resolve_report_dir()

    @classmethod
    def set_report_dir(cls, report_dir: Path) -> None:
        """Persist report directory to Settings."""
        Settings.set(REPORT_DIR_PATH_KEY, str(Path(report_dir).expanduser()))

    @classmethod
    def get_stats(cls) -> ProvisionStats:
        """Return accumulated provisioning statistics."""
        try:
            report_dir = cls._resolve_report_dir()
        except ProvisionReporterError:
            return ProvisionStats(
                success_count=0,
                error_count=0,
                total_count=0,
            )

        try:
            document = cls._read_stats_document(report_dir)
            counts = document.get("counts", {})

            success_count = counts.get("success", 0)
            error_count = counts.get("error", 0)

            if not isinstance(success_count, int) or isinstance(success_count, bool):
                success_count = 0
            if not isinstance(error_count, int) or isinstance(error_count, bool):
                error_count = 0

            return ProvisionStats(
                success_count=success_count,
                error_count=error_count,
                total_count=success_count + error_count,
            )

        except Exception as exc:
            raise ProvisionReporterError(
                "Failed to read provisioning statistics."
            ) from exc

    @classmethod
    def write(
        cls,
        report: dict[str, Any],
        schema: FactoryDataSchema | None = None,
    ) -> Path:
        """Normalize and write one report file."""
        try:
            report_dir = cls._resolve_report_dir()
            report_dir.mkdir(parents=True, exist_ok=True)

            content = cls._build_report_document(report, schema)
            file_path = cls._build_report_file_path(content, report_dir)

            with file_path.open("w", encoding="utf-8") as file:
                json.dump(content, file, indent=2, ensure_ascii=False, sort_keys=True)
                file.write("\n")

            cls._update_stats(report_dir=report_dir, report=content)
            return file_path

        except ProvisionReporterError:
            raise
        except Exception as exc:
            raise ProvisionReporterError(
                "Failed to write the provisioning result report file."
            ) from exc

    @classmethod
    def _resolve_report_dir(cls) -> Path:
        """Resolve report directory from Settings."""
        configured_path = Settings.get(REPORT_DIR_PATH_KEY)

        if not isinstance(configured_path, str) or not configured_path.strip():
            raise ProvisionReporterError(
                "Report directory is not configured. "
                f"Set '{REPORT_DIR_PATH_KEY}' in Settings."
            )

        report_dir = Path(configured_path).expanduser().resolve()

        if report_dir.exists() and not report_dir.is_dir():
            raise ProvisionReporterError(
                "Report path is not a directory. "
                f"path='{report_dir}'"
            )

        return report_dir

    @classmethod
    def _build_report_document(
        cls,
        report: dict[str, Any],
        schema: FactoryDataSchema | None,
    ) -> dict[str, Any]:
        """Build a JSON-safe report document."""
        content = cls._normalize_json_value(report)
        if not isinstance(content, dict):
            raise ProvisionReporterSerializationError(
                "The report root value must be a JSON object."
            )

        content = copy.deepcopy(content)

        injected_data = content.get("injected_data")
        if isinstance(injected_data, dict):
            content["injected_data"] = cls._normalize_injected_data(
                injected_data=injected_data,
                schema=schema,
            )

        content["written_at"] = cls._build_iso_utc_now()
        return content

    @classmethod
    def _normalize_injected_data(
        cls,
        injected_data: dict[str, Any],
        schema: FactoryDataSchema | None,
    ) -> dict[str, Any]:
        """Normalize injected_data values."""
        normalized: dict[str, Any] = {}

        for field_name, value in injected_data.items():
            normalized[field_name] = cls._normalize_injected_field_value(
                field_name=field_name,
                value=value,
                schema=schema,
            )

        return normalized

    @classmethod
    def _normalize_injected_field_value(
        cls,
        field_name: str,
        value: Any,
        schema: FactoryDataSchema | None,
    ) -> Any:
        """Normalize one injected_data field value."""
        if schema is None:
            return cls._normalize_json_value(value)

        try:
            field_schema = schema.get_field(field_name)
        except FactoryDataSchemaFieldError:
            return cls._normalize_json_value(value)

        field_type = field_schema.get("type")
        pattern = field_schema.get("pattern")

        if field_type == "string" and pattern == "^[0-9A-Fa-f]+$":
            return cls._normalize_hex_like_value(field_name, value)

        return cls._normalize_json_value(value)

    @classmethod
    def _normalize_hex_like_value(cls, field_name: str, value: Any) -> str:
        """Normalize a hex-like value into an uppercase hex string."""
        if isinstance(value, bytes):
            return value.hex().upper()

        if isinstance(value, bytearray):
            return bytes(value).hex().upper()

        if isinstance(value, list):
            try:
                return bytes(value).hex().upper()
            except Exception as exc:
                raise ProvisionReporterSerializationError(
                    f"Failed to normalize field '{field_name}' from byte list."
                ) from exc

        if isinstance(value, str):
            try:
                normalized = "".join(value.strip().split())
                bytes.fromhex(normalized)
                return normalized.upper()
            except Exception as exc:
                raise ProvisionReporterSerializationError(
                    f"Failed to normalize field '{field_name}' from hex string."
                ) from exc

        raise ProvisionReporterSerializationError(
            f"Field '{field_name}' must be bytes, bytearray, byte list, or hex string."
        )

    @classmethod
    def _normalize_json_value(cls, value: Any) -> Any:
        """Convert a Python value into a JSON-safe value."""
        if value is None:
            return None

        if isinstance(value, (bool, int, float, str)):
            return value

        if isinstance(value, bytes):
            return value.hex().upper()

        if isinstance(value, bytearray):
            return bytes(value).hex().upper()

        if isinstance(value, Path):
            return str(value)

        if isinstance(value, datetime):
            if value.tzinfo is None:
                return value.replace(tzinfo=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        if isinstance(value, dict):
            normalized_dict: dict[str, Any] = {}
            for key, item in value.items():
                if not isinstance(key, str):
                    raise ProvisionReporterSerializationError(
                        "All JSON object keys must be strings."
                    )
                normalized_dict[key] = cls._normalize_json_value(item)
            return normalized_dict

        if isinstance(value, (list, tuple)):
            return [cls._normalize_json_value(item) for item in value]

        raise ProvisionReporterSerializationError(
            f"Unsupported value type for JSON serialization: {type(value).__name__}"
        )

    @classmethod
    def _build_report_file_path(cls, report: dict[str, Any], report_dir: Path) -> Path:
        """Build output file path for a report document."""
        timestamp = cls._build_file_timestamp()
        index = report.get("index")

        result_value = report.get("result")
        success_value = report.get("success")

        if isinstance(result_value, str):
            result_text = result_value.strip().lower()
        elif isinstance(success_value, bool):
            result_text = "success" if success_value else "fail"
        else:
            result_text = "unknown"

        if isinstance(index, int) and not isinstance(index, bool):
            index_text = f"{index:06d}"
        else:
            index_text = "noindex"

        file_name = f"{timestamp}_{index_text}_{result_text}.json"
        return report_dir / file_name

    @classmethod
    def _stats_file_path(cls, report_dir: Path) -> Path:
        """Return the stats file path under the report directory."""
        return report_dir / _STATS_FILE_NAME

    @classmethod
    def _read_stats_document(cls, report_dir: Path) -> dict[str, Any]:
        """Read the raw stats document, or return a default one."""
        file_path = cls._stats_file_path(report_dir)

        if not file_path.exists():
            return {
                "version": 1,
                "counts": {
                    "success": 0,
                    "error": 0,
                },
                "updated_at": cls._build_iso_utc_now(),
            }

        try:
            with file_path.open("r", encoding="utf-8") as file:
                content = json.load(file)
        except Exception as exc:
            raise ProvisionReporterError(
                f"Failed to read stats file. path='{file_path}'"
            ) from exc

        if not isinstance(content, dict):
            raise ProvisionReporterError(
                f"Stats file root must be a JSON object. path='{file_path}'"
            )

        counts = content.get("counts")
        if not isinstance(counts, dict):
            content["counts"] = {"success": 0, "error": 0}

        return content

    @classmethod
    def _write_stats_document(cls, report_dir: Path, content: dict[str, Any]) -> None:
        """Write the raw stats document."""
        file_path = cls._stats_file_path(report_dir)

        try:
            with file_path.open("w", encoding="utf-8") as file:
                json.dump(content, file, indent=2, ensure_ascii=False, sort_keys=True)
                file.write("\n")
        except Exception as exc:
            raise ProvisionReporterError(
                f"Failed to write stats file. path='{file_path}'"
            ) from exc

    @classmethod
    def _update_stats(cls, report_dir: Path, report: dict[str, Any]) -> None:
        """Update accumulated stats from one written report."""
        document = cls._read_stats_document(report_dir)

        counts = document.setdefault("counts", {})
        success_count = counts.get("success", 0)
        error_count = counts.get("error", 0)

        if not isinstance(success_count, int) or isinstance(success_count, bool):
            success_count = 0
        if not isinstance(error_count, int) or isinstance(error_count, bool):
            error_count = 0

        result_value = report.get("result")
        success_value = report.get("success")

        is_success: bool | None = None

        if isinstance(success_value, bool):
            is_success = success_value
        elif isinstance(result_value, str):
            result_text = result_value.strip().lower()
            if result_text in {"success", "ok", "pass"}:
                is_success = True
            elif result_text in {"fail", "failed", "error"}:
                is_success = False

        if is_success is True:
            success_count += 1
        elif is_success is False:
            error_count += 1

        document["version"] = 1
        document["counts"] = {
            "success": success_count,
            "error": error_count,
        }
        document["updated_at"] = cls._build_iso_utc_now()

        cls._write_stats_document(report_dir, document)

    @classmethod
    def _build_file_timestamp(cls) -> str:
        """Build a human-readable UTC timestamp for file names."""
        return datetime.now(timezone.utc).strftime("%Y-%m-%d_%H-%M-%S")

    @classmethod
    def _build_iso_utc_now(cls) -> str:
        """Build ISO-like UTC timestamp string."""
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
