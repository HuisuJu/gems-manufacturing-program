from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, Mapping

from .retriever import Retriever


class FactoryDataProviderError(Exception):
    """
    Base exception for factory data provider failures.
    """


class FactoryDataProviderConfigurationError(FactoryDataProviderError):
    """
    Raised when the provider configuration is missing or invalid.
    """


class FactoryDataProviderInProgressError(FactoryDataProviderError):
    """
    Raised when pull() is called while a previous result has not been reported yet.
    """


class FactoryDataProviderReportError(FactoryDataProviderError):
    """
    Raised when report() is called without an active pulled result.
    """


class FactoryDataProviderConflictError(FactoryDataProviderError):
    """
    Raised when multiple retrievers return conflicting values for the same field.
    """


class FactoryDataProvider:
    """
    Orchestrate factory data retrieval across registered retrievers.

    Responsibilities:
    - resolve the model schema from base.schema.json and {model}.schema.json
    - call registered retrievers
    - merge partial results
    - verify that all required fields are present
    - keep the pulled result in progress until report() is called
    - propagate the final result to retrievers that support report()

    The provider itself does not perform full JSON Schema validation. It uses
    the resolved schema primarily for field planning and completeness checks.
    """

    BASE_SCHEMA_FILENAME = "base.schema.json"

    def __init__(
        self,
        schema_directory: str | Path | None = None,
        model_name: str | None = None,
        retrievers: list[Retriever] | None = None,
    ) -> None:
        """
        Initialize the factory data provider.

        Args:
            schema_directory: Directory containing base.schema.json and
                model schema files.
            model_name: Current target model name, e.g. "doorlock".
            retrievers: Initial retriever list.
        """
        self._schema_directory: Path | None = None
        self._model_name: str | None = None
        self._retrievers: list[Retriever] = list(retrievers) if retrievers is not None else []

        self._in_progress_data: dict[str, Any] | None = None
        self._reportable_retrievers: list[Any] = []

        if schema_directory is not None:
            self.set_schema_directory(schema_directory)

        if model_name is not None:
            self.set_model_name(model_name)

    @property
    def schema_directory(self) -> Path | None:
        """
        Return the configured schema directory.
        """
        return self._schema_directory

    @property
    def model_name(self) -> str | None:
        """
        Return the configured model name.
        """
        return self._model_name

    @property
    def retrievers(self) -> tuple[Retriever, ...]:
        """
        Return the registered retrievers.
        """
        return tuple(self._retrievers)

    def set_schema_directory(self, directory: str | Path) -> None:
        """
        Configure the schema directory.

        Args:
            directory: Schema directory path.

        Raises:
            FactoryDataProviderConfigurationError: If the path is invalid.
        """
        path = Path(directory).expanduser().resolve()

        if not path.exists():
            raise FactoryDataProviderConfigurationError(
                "The schema directory does not exist."
            )

        if not path.is_dir():
            raise FactoryDataProviderConfigurationError(
                "The schema path is not a directory."
            )

        self._schema_directory = path

    def set_model_name(self, model_name: str) -> None:
        """
        Configure the target model name.

        Args:
            model_name: Model name used to resolve {model}.schema.json.

        Raises:
            FactoryDataProviderConfigurationError: If the model name is empty.
        """
        normalized = model_name.strip()
        if not normalized:
            raise FactoryDataProviderConfigurationError(
                "The model name must not be empty."
            )

        self._model_name = normalized

    def add_retriever(self, retriever: Retriever) -> None:
        """
        Register a retriever.

        Args:
            retriever: Retriever instance to add.
        """
        self._retrievers.append(retriever)

    def clear_retrievers(self) -> None:
        """
        Remove all registered retrievers.
        """
        self._retrievers.clear()

    def pull(self) -> dict[str, Any]:
        """
        Pull factory data from all registered retrievers.

        The result remains in progress until report() is called.

        Returns:
            A merged factory data dictionary.

        Raises:
            FactoryDataProviderInProgressError: If a previous result has not
                been reported yet.
            FactoryDataProviderError: If schema resolution, retrieval, merging,
                or completeness checks fail.
        """
        if self._in_progress_data is not None:
            raise FactoryDataProviderInProgressError(
                "Factory data is already in progress. Report it before pulling another one."
            )

        schema = self._load_resolved_schema()
        merged: dict[str, Any] = {}
        reportable_retrievers: list[Any] = []

        try:
            for retriever in self._retrievers:
                partial = retriever.fetch(schema)
                self._merge_partial_result(
                    merged=merged,
                    partial=partial,
                    retriever_name=retriever.name,
                )

                if hasattr(retriever, "report") and callable(getattr(retriever, "report")):
                    reportable_retrievers.append(retriever)

            self._check_required_fields(schema=schema, data=merged)

        except Exception as exc:
            self._rollback_retrievers(reportable_retrievers)
            if isinstance(exc, FactoryDataProviderError):
                raise
            raise FactoryDataProviderError(
                f"Failed to pull factory data: {exc}"
            ) from exc

        self._in_progress_data = copy.deepcopy(merged)
        self._reportable_retrievers = reportable_retrievers
        return copy.deepcopy(merged)

    def report(self, is_success: bool) -> None:
        """
        Report the final provisioning result for the current in-progress data.

        Args:
            is_success: True if provisioning succeeded, otherwise False.

        Raises:
            FactoryDataProviderReportError: If no factory data is currently in
                progress.
            FactoryDataProviderError: If a retriever report fails.
        """
        if self._in_progress_data is None:
            raise FactoryDataProviderReportError(
                "There is no factory data in progress to report."
            )

        try:
            for retriever in self._reportable_retrievers:
                retriever.report(is_success=is_success)
        except Exception as exc:
            raise FactoryDataProviderError(
                f"Failed to report the factory data result: {exc}"
            ) from exc
        finally:
            self._in_progress_data = None
            self._reportable_retrievers = []

    def get_resolved_schema(self) -> dict[str, Any]:
        """
        Return the resolved schema for the configured model.

        Returns:
            A deep copy of the resolved schema dictionary.
        """
        return copy.deepcopy(self._load_resolved_schema())

    def _load_resolved_schema(self) -> dict[str, Any]:
        """
        Load and resolve the schema for the configured model.

        Resolution rules:
        - base.schema.json provides common structure and property definitions
        - {model}.schema.json overrides model-specific properties
        - required comes from the model schema
        - base type / additionalProperties / $schema are preserved

        Returns:
            The resolved schema dictionary.

        Raises:
            FactoryDataProviderConfigurationError: If configuration or schema
                files are missing or invalid.
        """
        schema_directory = self._require_schema_directory()
        model_name = self._require_model_name()

        base_path = schema_directory / self.BASE_SCHEMA_FILENAME
        model_path = schema_directory / f"{model_name}.schema.json"

        base_schema = self._load_json_object(base_path, "base schema")
        model_schema = self._load_json_object(model_path, "model schema")

        base_properties = base_schema.get("properties", {})
        if not isinstance(base_properties, dict):
            raise FactoryDataProviderConfigurationError(
                "The base schema must define a properties object."
            )

        model_properties = model_schema.get("properties", {})
        if not isinstance(model_properties, dict):
            raise FactoryDataProviderConfigurationError(
                "The model schema must define a properties object."
            )

        model_required = model_schema.get("required", [])
        if not isinstance(model_required, list) or not all(
            isinstance(field, str) for field in model_required
        ):
            raise FactoryDataProviderConfigurationError(
                "The model schema must define a required field list of strings."
            )

        resolved = copy.deepcopy(base_schema)
        resolved["title"] = model_schema.get("title", base_schema.get("title"))
        resolved["required"] = copy.deepcopy(model_required)
        resolved["properties"] = copy.deepcopy(base_properties)

        for field_name, field_schema in model_properties.items():
            if not isinstance(field_name, str) or not isinstance(field_schema, dict):
                raise FactoryDataProviderConfigurationError(
                    "The model schema properties must use string keys and object values."
                )

            merged_field_schema = copy.deepcopy(resolved["properties"].get(field_name, {}))
            if not isinstance(merged_field_schema, dict):
                merged_field_schema = {}

            merged_field_schema.update(copy.deepcopy(field_schema))
            resolved["properties"][field_name] = merged_field_schema

        return resolved

    def _load_json_object(self, path: Path, label: str) -> dict[str, Any]:
        """
        Load a JSON file and require that it contains a JSON object.

        Args:
            path: JSON file path.
            label: Human-readable label used in error messages.

        Returns:
            Parsed JSON object.

        Raises:
            FactoryDataProviderConfigurationError: If loading fails.
        """
        if not path.exists():
            raise FactoryDataProviderConfigurationError(
                f"The {label} file does not exist: {path.name}"
            )

        if not path.is_file():
            raise FactoryDataProviderConfigurationError(
                f"The {label} path is not a file: {path.name}"
            )

        try:
            with path.open("r", encoding="utf-8") as file:
                data = json.load(file)
        except OSError as exc:
            raise FactoryDataProviderConfigurationError(
                f"Failed to read the {label} file: {path.name}"
            ) from exc
        except json.JSONDecodeError as exc:
            raise FactoryDataProviderConfigurationError(
                f"The {label} file is not a valid JSON file: {path.name}"
            ) from exc

        if not isinstance(data, dict):
            raise FactoryDataProviderConfigurationError(
                f"The {label} file must contain a JSON object: {path.name}"
            )

        return data

    def _check_required_fields(self, schema: Mapping[str, Any], data: Mapping[str, Any]) -> None:
        """
        Check that all required fields declared by the schema are present.

        Args:
            schema: Resolved schema.
            data: Merged factory data.

        Raises:
            FactoryDataProviderError: If any required field is missing.
        """
        required = schema.get("required", [])
        if not isinstance(required, list):
            raise FactoryDataProviderError(
                "The resolved schema does not contain a valid required field list."
            )

        missing = [field for field in required if field not in data]
        if missing:
            missing_fields = ", ".join(sorted(missing))
            raise FactoryDataProviderError(
                f"The pulled factory data is missing required fields: {missing_fields}"
            )

    def _merge_partial_result(
        self,
        merged: dict[str, Any],
        partial: Mapping[str, Any],
        retriever_name: str,
    ) -> None:
        """
        Merge a partial retriever result into the accumulated result.

        If the same field appears more than once:
        - identical values are allowed
        - different values raise a conflict error

        Args:
            merged: Accumulated factory data.
            partial: Partial retriever output.
            retriever_name: Human-readable retriever name.

        Raises:
            FactoryDataProviderError: If the partial result is invalid.
            FactoryDataProviderConflictError: If a conflicting value is found.
        """
        if not isinstance(partial, Mapping):
            raise FactoryDataProviderError(
                f"Retriever '{retriever_name}' returned an invalid result."
            )

        for field_name, value in partial.items():
            if not isinstance(field_name, str):
                raise FactoryDataProviderError(
                    f"Retriever '{retriever_name}' returned a non-string field name."
                )

            if field_name in merged and merged[field_name] != value:
                raise FactoryDataProviderConflictError(
                    f"Retriever '{retriever_name}' returned a conflicting value for field '{field_name}'."
                )

            merged[field_name] = value

    def _rollback_retrievers(self, retrievers: list[Any]) -> None:
        """
        Best-effort rollback for retrievers that support report().

        Args:
            retrievers: Retrievers to roll back using report(False).
        """
        for retriever in retrievers:
            try:
                retriever.report(is_success=False)
            except Exception:
                pass

    def _require_schema_directory(self) -> Path:
        """
        Return the configured schema directory.

        Raises:
            FactoryDataProviderConfigurationError: If not configured.
        """
        if self._schema_directory is None:
            raise FactoryDataProviderConfigurationError(
                "The schema directory has not been configured."
            )

        return self._schema_directory

    def _require_model_name(self) -> str:
        """
        Return the configured model name.

        Raises:
            FactoryDataProviderConfigurationError: If not configured.
        """
        if self._model_name is None:
            raise FactoryDataProviderConfigurationError(
                "The model name has not been configured."
            )

        return self._model_name