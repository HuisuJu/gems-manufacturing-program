from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from system import ModelName


class FactoryDataSchemaError(Exception):
    """Base schema error."""


class FactoryDataSchemaFileError(FactoryDataSchemaError):
    """Schema file error."""


class FactoryDataSchemaFieldError(FactoryDataSchemaError):
    """Schema field error."""


class FactoryDataSchema:
    """Load and resolve factory-data schema for one model."""

    schema: dict[str, Any]
    _fields: dict[str, dict[str, Any]]
    _required_fields: list[str]

    def __init__(
        self,
        base_schema_file: Path,
        model_schema_file: Path,
    ) -> None:
        """Initialize and resolve schema files."""
        self.schema = self._load(base_schema_file, model_schema_file)

        self._fields = self.schema.get("properties", {})
        self._required_fields = list(self.schema.get("required", []))

    @property
    def fields(self) -> dict[str, dict[str, Any]]:
        """Return all resolved field schemas."""
        return copy.deepcopy(self._fields)

    @property
    def required_fields(self) -> list[str]:
        """Return required field names."""
        return list(self._required_fields)

    def get_model(self) -> ModelName:
        """Return the model name defined in the schema."""
        model = self.schema.get("model")
        if not isinstance(model, str) or not model:
            raise FactoryDataSchemaError(
                "The schema must define a model string."
            )

        try:
            return ModelName(model)
        except ValueError as exc:
            raise FactoryDataSchemaError(
                f"The schema defines an unsupported model value: {model!r}"
            ) from exc

    def get_field(self, field_name: str) -> dict[str, Any]:
        """Return one resolved field schema."""
        if field_name not in self._fields:
            raise FactoryDataSchemaFieldError(
                f"Schema field '{field_name}' is not defined."
            )

        field = self._fields[field_name]
        if not isinstance(field, dict):
            raise FactoryDataSchemaFieldError(
                f"Schema field '{field_name}' is not a valid schema object."
            )

        return copy.deepcopy(field)

    def get_integer(self, field_name: str) -> int:
        """Return integer const for a field."""
        field_schema = self.get_field(field_name)

        if field_schema.get("type") != "integer":
            raise FactoryDataSchemaFieldError(
                f"Schema field '{field_name}' must have type 'integer'."
            )

        if "const" not in field_schema:
            raise FactoryDataSchemaFieldError(
                f"Schema field '{field_name}' does not define a constant integer value."
            )

        value = field_schema["const"]
        if not isinstance(value, int) or isinstance(value, bool):
            raise FactoryDataSchemaFieldError(
                f"Schema field '{field_name}' const value must be an integer."
            )

        return value

    def get_string(self, field_name: str) -> str:
        """Return string const for a field."""
        field_schema = self.get_field(field_name)

        if field_schema.get("type") != "string":
            raise FactoryDataSchemaFieldError(
                f"Schema field '{field_name}' must have type 'string'."
            )

        if "const" not in field_schema:
            raise FactoryDataSchemaFieldError(
                f"Schema field '{field_name}' does not define a constant string value."
            )

        value = field_schema["const"]
        if not isinstance(value, str):
            raise FactoryDataSchemaFieldError(
                f"Schema field '{field_name}' const value must be a string."
            )

        return value

    def get_size(self, field_name: str) -> int:
        """Return fixed hex-string field size in bytes."""
        field_schema = self.get_field(field_name)

        if field_schema.get("type") != "string":
            raise FactoryDataSchemaFieldError(
                f"Schema field '{field_name}' must have type 'string'."
            )

        min_length = field_schema.get("minLength")
        max_length = field_schema.get("maxLength")

        if not isinstance(min_length, int) or not isinstance(max_length, int):
            raise FactoryDataSchemaFieldError(
                f"Schema field '{field_name}' must define both minLength and maxLength."
            )

        if min_length != max_length:
            raise FactoryDataSchemaFieldError(
                f"Schema field '{field_name}' must define a fixed hex string length."
            )

        if min_length <= 0 or (min_length % 2) != 0:
            raise FactoryDataSchemaFieldError(
                f"Schema field '{field_name}' must define an even "
                "positive hex string length."
            )

        return min_length // 2

    def _load(
        self,
        base_schema_file: Path,
        model_schema_file: Path,
    ) -> dict[str, Any]:
        """Load base/model schema and merge them."""
        base_schema = self._load_json(base_schema_file)
        model_schema = self._load_json(model_schema_file)

        base_properties = base_schema.get("properties", {})
        if not isinstance(base_properties, dict):
            raise FactoryDataSchemaFileError(
                "The base schema must define a properties object."
            )

        model_properties = model_schema.get("properties", {})
        if not isinstance(model_properties, dict):
            raise FactoryDataSchemaFileError(
                "The model schema must define a properties object."
            )

        required_fields = model_schema.get("required", [])
        if not isinstance(required_fields, list) or not all(
            isinstance(field, str) for field in required_fields
        ):
            raise FactoryDataSchemaFileError(
                "The model schema must define a required field list of strings."
            )

        model_name = model_schema.get("model")
        if not isinstance(model_name, str) or not model_name:
            raise FactoryDataSchemaFileError(
                "The model schema must define a model string."
            )

        resolved_schema = copy.deepcopy(base_schema)
        resolved_schema["model"] = model_name
        resolved_schema["title"] = model_schema.get("title")
        resolved_schema["required"] = required_fields

        resolved_properties = resolved_schema.get("properties", {})
        if not isinstance(resolved_properties, dict):
            raise FactoryDataSchemaFileError(
                "The resolved schema must define a properties object."
            )

        for field_name, field_schema in model_properties.items():
            if not isinstance(field_name, str) or not isinstance(field_schema, dict):
                raise FactoryDataSchemaFileError(
                    "The model schema properties must use string keys "
                    "and object values."
                )

            if field_name not in resolved_properties:
                resolved_properties[field_name] = copy.deepcopy(field_schema)
                continue

            base_field_schema = resolved_properties[field_name]
            if not isinstance(base_field_schema, dict):
                raise FactoryDataSchemaFileError(
                    f"The base schema field '{field_name}' must be an object."
                )

            merged_field_schema = copy.deepcopy(base_field_schema)
            merged_field_schema.update(field_schema)
            resolved_properties[field_name] = merged_field_schema

        return resolved_schema

    def _load_json(self, path: Path) -> dict[str, Any]:
        """Load a JSON object from file."""
        if not path.exists():
            raise FactoryDataSchemaFileError(f"The {path.name} file does not exist.")
        if not path.is_file():
            raise FactoryDataSchemaFileError(f"The {path.name} path is not a file.")

        try:
            with path.open("r", encoding="utf-8") as file:
                data = json.load(file)
        except OSError as exc:
            raise FactoryDataSchemaFileError(
                f"Failed to read the {path.name} file."
            ) from exc
        except json.JSONDecodeError as exc:
            raise FactoryDataSchemaFileError(
                f"The {path.name} file is not a valid JSON file."
            ) from exc

        if not isinstance(data, dict):
            raise FactoryDataSchemaFileError(
                f"The {path.name} file must contain a JSON object."
            )

        return data
