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

    def __init__(
        self,
        schema_dir: Path,
        model_name: ModelName,
    ) -> None:
        """Initialize and resolve schema files."""
        base_schema_path = schema_dir / "base.schema.json"
        model_schema_path = schema_dir / (model_name.value + ".schema.json")

        self._schema = self._load(base_schema_path, model_schema_path)

    @property

    def required_fields(self) -> list[str]:
        """Required field names."""
        required = self._schema.get("required", [])
        if not isinstance(required, list) or not all(
            isinstance(field, str) for field in required
        ):
            raise FactoryDataSchemaFileError(
                "The resolved schema does not define a valid required field list."
            )
        return list(required)

    @property

    def properties(self) -> dict[str, dict[str, Any]]:
        """Resolved field schemas."""
        properties_schema = self._schema.get("properties", {})
        if not isinstance(properties_schema, dict):
            raise FactoryDataSchemaFileError(
                "The resolved schema does not define a valid properties object."
            )

        properties: dict[str, dict[str, Any]] = {}
        for field_name, field_schema in properties_schema.items():
            if isinstance(field_name, str) and isinstance(field_schema, dict):
                properties[field_name] = copy.deepcopy(field_schema)

        return properties

    def get_field(self, field_name: str) -> dict[str, Any]:
        """Return one resolved field schema."""
        properties = self.properties
        if field_name not in properties:
            raise FactoryDataSchemaFieldError(
                f"Schema field '{field_name}' is not defined."
            )

        field = properties[field_name]
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
                "Schema field "
                f"'{field_name}' does not define a constant integer value."
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
                "Schema field "
                f"'{field_name}' does not define a constant string value."
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
                f"Schema field '{field_name}' must define both "
                "minLength and maxLength."
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
        base_schema_path: Path,
        model_schema_path: Path,
    ) -> dict[str, Any]:
        """Load base/model schema and merge them."""
        base_schema = self._load_json(base_schema_path)
        model_schema = self._load_json(model_schema_path)

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

        model_required = model_schema.get("required", [])
        if not isinstance(model_required, list) or not all(
            isinstance(field, str) for field in model_required
        ):
            raise FactoryDataSchemaFileError(
                "The model schema must define a required field list of strings."
            )

        resolved = copy.deepcopy(base_schema)
        resolved["title"] = model_schema.get("title", base_schema.get("title"))
        resolved["required"] = copy.deepcopy(model_required)
        resolved["properties"] = copy.deepcopy(base_properties)

        for field_name, field_schema in model_properties.items():
            if not isinstance(field_name, str) or not isinstance(field_schema, dict):
                raise FactoryDataSchemaFileError(
                    "The model schema properties must use string keys "
                    "and object values."
                )

            merged_field_schema = copy.deepcopy(
                resolved["properties"].get(field_name, {})
            )
            if not isinstance(merged_field_schema, dict):
                merged_field_schema = {}

            merged_field_schema.update(copy.deepcopy(field_schema))
            resolved["properties"][field_name] = merged_field_schema

        return resolved

    def _load_json(self, path: Path) -> dict[str, Any]:
        """Load a JSON object from file."""
        if not path.exists():
            raise FactoryDataSchemaFileError(
                f"The {path.name} file does not exist."
            )

        if not path.is_file():
            raise FactoryDataSchemaFileError(
                f"The {path.name} path is not a file."
            )

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
