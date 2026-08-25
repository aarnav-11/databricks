"""Small, parameterized adapters for the POC's Unity Catalog functions."""

from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from databricks.sdk import WorkspaceClient
from databricks.sdk.service.sql import StatementParameterListItem

IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _value(value: Any, key: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        return value.get(key, default)
    return getattr(value, key, default)


def _jsonable(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _jsonable(nested) for key, nested in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(nested) for nested in value]
    return value


class UCFunctionClient:
    """Execute only known table-valued UC functions through SQL Statement Execution."""

    def __init__(
        self,
        workspace_client: WorkspaceClient | None = None,
        *,
        warehouse_id: str | None = None,
        catalog: str | None = None,
        schema: str | None = None,
    ) -> None:
        self.workspace_client = workspace_client or WorkspaceClient()
        self.warehouse_id = warehouse_id or self._required_env("WAREHOUSE_ID")
        self.catalog = catalog or self._env("FRAUD_CATALOG", "workspace")
        self.schema = schema or self._env("FRAUD_SCHEMA", "insurance_fraud_poc")
        self._validate_identifier(self.catalog, "catalog")
        self._validate_identifier(self.schema, "schema")

    @staticmethod
    def _env(name: str, default: str) -> str:
        import os

        return os.getenv(name, default)

    @classmethod
    def _required_env(cls, name: str) -> str:
        value = cls._env(name, "")
        if not value:
            raise RuntimeError(f"Missing required environment variable: {name}")
        return value

    @staticmethod
    def _validate_identifier(value: str, label: str) -> None:
        if not IDENTIFIER_PATTERN.fullmatch(value):
            raise ValueError(f"Invalid {label} identifier")

    def call(self, function_name: str, parameters: dict[str, str] | None = None) -> dict[str, Any]:
        """Call a registered POC function and return rows with column names."""

        parameters = parameters or {}
        self._validate_identifier(function_name, "function")
        placeholders = ", ".join(f":{name}" for name in parameters)
        statement = (
            f"SELECT * FROM {self.catalog}.{self.schema}.{function_name}({placeholders})"
        )
        response = self.workspace_client.statement_execution.execute_statement(
            warehouse_id=self.warehouse_id,
            catalog=self.catalog,
            schema=self.schema,
            wait_timeout="30s",
            statement=statement,
            parameters=[
                StatementParameterListItem(name=name, value=str(value))
                for name, value in parameters.items()
            ],
        )
        payload = response if isinstance(response, dict) else response.as_dict()
        status = _value(payload, "status", {}) or {}
        state = _value(status, "state")
        if state != "SUCCEEDED":
            return {
                "status": "failed",
                "function": function_name,
                "details": _jsonable(status),
            }

        manifest = _value(payload, "manifest", {}) or {}
        result = _value(payload, "result", {}) or {}
        schema_payload = _value(manifest, "schema", {}) or {}
        columns_payload = _value(schema_payload, "columns", []) or []
        columns = [str(_value(column, "name", "column")) for column in columns_payload]
        data_array = _value(result, "data_array", []) or []
        rows = []
        for values in data_array:
            rows.append(
                {
                    column: _jsonable(values[index]) if index < len(values) else None
                    for index, column in enumerate(columns)
                }
            )

        return {
            "status": "ok",
            "function": function_name,
            "columns": columns,
            "rows": rows,
            "row_count": len(rows),
        }
