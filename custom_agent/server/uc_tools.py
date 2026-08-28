"""Safe, parameterized reads from App-linked Unity Catalog tables."""

from __future__ import annotations

import os
import re
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Iterable

from databricks.sdk import WorkspaceClient
from databricks.sdk.service.sql import StatementParameterListItem

COLUMN_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
TABLE_PART_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")


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


def _find_values(value: Any, keys: Iterable[str]) -> dict[str, list[str]]:
    wanted = {key.lower() for key in keys}
    found: dict[str, list[str]] = {key: [] for key in wanted}

    def visit(item: Any) -> None:
        if isinstance(item, dict):
            for key, nested in item.items():
                normalized = str(key).lower()
                if normalized in wanted and nested is not None and not isinstance(nested, (dict, list)):
                    text = str(nested)
                    if text not in found[normalized]:
                        found[normalized].append(text)
                visit(nested)
        elif isinstance(item, (list, tuple)):
            for nested in item:
                visit(nested)

    visit(value)
    return found


class UCTableClient:
    """Read linked UC tables through a SQL warehouse when one is available."""

    def __init__(
        self,
        workspace_client: WorkspaceClient | None = None,
        *,
        warehouse_id: str | None = None,
    ) -> None:
        self.workspace_client = workspace_client or WorkspaceClient()
        self.warehouse_id = warehouse_id if warehouse_id is not None else os.getenv("WAREHOUSE_ID", "")

    @staticmethod
    def _quoted_table(full_name: str) -> str:
        parts = full_name.split(".")
        if len(parts) != 3 or any(not TABLE_PART_PATTERN.fullmatch(part) for part in parts):
            raise ValueError("UC table resource must resolve to catalog.schema.table")
        return ".".join(f"`{part}`" for part in parts)

    @staticmethod
    def _quoted_column(name: str) -> str:
        if not COLUMN_PATTERN.fullmatch(name):
            raise ValueError(f"Invalid lookup column: {name!r}")
        return f"`{name}`"

    def _columns(self, table_name: str) -> dict[str, str]:
        table = self.workspace_client.tables.get(full_name=table_name)
        columns = _value(table, "columns", []) or []
        return {
            str(_value(column, "name")): str(_value(column, "name"))
            for column in columns
            if _value(column, "name")
        }

    @staticmethod
    def _lookup_key(
        *,
        actual_columns: dict[str, str],
        lookup_columns: Iterable[str],
        claim_id: str,
        evidence: Any,
    ) -> tuple[str, list[str]]:
        column_by_lower = {name.lower(): name for name in actual_columns}
        candidates = tuple(lookup_columns)
        related_values = _find_values(evidence, candidates)
        for candidate in candidates:
            actual = column_by_lower.get(candidate.lower())
            if not actual:
                continue
            if candidate.lower() in {"claim_id", "claim_number"}:
                values = [claim_id]
            else:
                values = related_values[candidate.lower()]
            if values:
                return actual, values[:10]
        return "", []

    def _execute_rows(
        self,
        *,
        table_name: str,
        statement: str,
        parameters: list[StatementParameterListItem],
        operation: str,
        metadata: dict[str, Any],
    ) -> dict[str, Any]:
        response = self.workspace_client.statement_execution.execute_statement(
            warehouse_id=self.warehouse_id,
            wait_timeout="30s",
            statement=statement,
            parameters=parameters,
        )
        payload = response if isinstance(response, dict) else response.as_dict()
        status = _value(payload, "status", {}) or {}
        if str(_value(status, "state", "")) != "SUCCEEDED":
            return {
                "status": "failed",
                "resource": table_name,
                "operation": operation,
                "details": _jsonable(status),
            }

        manifest = _value(payload, "manifest", {}) or {}
        result = _value(payload, "result", {}) or {}
        schema_payload = _value(manifest, "schema", {}) or {}
        columns_payload = _value(schema_payload, "columns", []) or []
        result_columns = [str(_value(column, "name", "column")) for column in columns_payload]
        rows = [
            {
                column: _jsonable(values[index]) if index < len(values) else None
                for index, column in enumerate(result_columns)
            }
            for values in (_value(result, "data_array", []) or [])
        ]
        return {
            "status": "ok",
            "resource": table_name,
            "operation": operation,
            **metadata,
            "columns": result_columns,
            "rows": rows,
            "row_count": len(rows),
        }

    def query_for_claim(
        self,
        *,
        table_name: str,
        claim_id: str,
        evidence: Any,
        lookup_columns: Iterable[str],
        limit: int = 20,
    ) -> dict[str, Any]:
        """Find a usable relationship key and return a bounded table slice."""

        if not self.warehouse_id:
            return {
                "status": "unavailable",
                "resource": table_name,
                "missing_resource": "WAREHOUSE_ID",
                "message": "Direct UC table reads require a linked SQL warehouse.",
            }

        quoted_table = self._quoted_table(table_name)
        try:
            actual_columns = self._columns(table_name)
        except Exception as exc:
            return {
                "status": "unavailable",
                "resource": table_name,
                "operation": "read_table_schema",
                "error": str(exc),
            }
        candidates = tuple(lookup_columns)
        lookup_column, lookup_values = self._lookup_key(
            actual_columns=actual_columns,
            lookup_columns=candidates,
            claim_id=claim_id,
            evidence=evidence,
        )

        if not lookup_column:
            return {
                "status": "missing_input",
                "resource": table_name,
                "operation": "query_table",
                "missing": "a related identifier matching one of: " + ", ".join(candidates),
                "available_columns": sorted(actual_columns),
            }

        placeholders = ", ".join(f":lookup_{index}" for index in range(len(lookup_values)))
        bounded_limit = max(1, min(int(limit), 100))
        statement = (
            f"SELECT * FROM {quoted_table} "
            f"WHERE CAST({self._quoted_column(lookup_column)} AS STRING) IN ({placeholders}) "
            f"LIMIT {bounded_limit}"
        )
        return self._execute_rows(
            table_name=table_name,
            statement=statement,
            parameters=[
                StatementParameterListItem(name=f"lookup_{index}", value=value)
                for index, value in enumerate(lookup_values)
            ],
            operation="query_table",
            metadata={"lookup_column": lookup_column, "lookup_values": lookup_values},
        )

    def query_metric_for_claim(
        self,
        *,
        table_name: str,
        claim_id: str,
        lookup_columns: Iterable[str],
        measure_columns: Iterable[str],
        limit: int = 20,
    ) -> dict[str, Any]:
        """Query a UC metric view using explicit MEASURE() expressions."""

        if not self.warehouse_id:
            return {
                "status": "unavailable",
                "resource": table_name,
                "missing_resource": "WAREHOUSE_ID",
                "message": "Metric-view reads require a linked SQL warehouse.",
            }

        quoted_table = self._quoted_table(table_name)
        try:
            actual_columns = self._columns(table_name)
        except Exception as exc:
            return {
                "status": "unavailable",
                "resource": table_name,
                "operation": "read_metric_schema",
                "error": str(exc),
            }

        candidates = tuple(lookup_columns)
        lookup_column, lookup_values = self._lookup_key(
            actual_columns=actual_columns,
            lookup_columns=candidates,
            claim_id=claim_id,
            evidence={},
        )
        if not lookup_column:
            return {
                "status": "missing_configuration",
                "resource": table_name,
                "operation": "query_metric_view",
                "missing": "a metric-view field matching one of: " + ", ".join(candidates),
                "available_columns": sorted(actual_columns),
            }

        column_by_lower = {name.lower(): name for name in actual_columns}
        measures = [
            column_by_lower[name.lower()]
            for name in measure_columns
            if name.lower() in column_by_lower
        ]
        if not measures:
            return {
                "status": "missing_configuration",
                "resource": table_name,
                "operation": "query_metric_view",
                "missing": "configured metric measures: " + ", ".join(measure_columns),
                "available_columns": sorted(actual_columns),
            }

        measure_sql = ", ".join(
            f"MEASURE({self._quoted_column(name)}) AS {self._quoted_column(name)}"
            for name in measures
        )
        placeholders = ", ".join(f":lookup_{index}" for index in range(len(lookup_values)))
        bounded_limit = max(1, min(int(limit), 100))
        quoted_lookup = self._quoted_column(lookup_column)
        statement = (
            f"SELECT {quoted_lookup}, {measure_sql} FROM {quoted_table} "
            f"WHERE CAST({quoted_lookup} AS STRING) IN ({placeholders}) "
            f"GROUP BY {quoted_lookup} LIMIT {bounded_limit}"
        )
        return self._execute_rows(
            table_name=table_name,
            statement=statement,
            parameters=[
                StatementParameterListItem(name=f"lookup_{index}", value=value)
                for index, value in enumerate(lookup_values)
            ],
            operation="query_metric_view",
            metadata={
                "lookup_column": lookup_column,
                "lookup_values": lookup_values,
                "measures": measures,
            },
        )


# Compatibility for older imports while the POC moves from UC functions to tables.
UCFunctionClient = UCTableClient
