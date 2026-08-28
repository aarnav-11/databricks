"""Adapter for a Databricks AI Search index linked to the App."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from databricks.sdk import WorkspaceClient


def _jsonable(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if hasattr(value, "as_dict"):
        return _jsonable(value.as_dict())
    if isinstance(value, dict):
        return {str(key): _jsonable(nested) for key, nested in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(nested) for nested in value]
    return value


class VectorSearchClient:
    def __init__(self, workspace_client: WorkspaceClient | None = None) -> None:
        self.workspace_client = workspace_client or WorkspaceClient()

    def search(self, *, index_name: str, query_text: str, num_results: int = 10) -> dict[str, Any]:
        try:
            response = self.workspace_client.vector_search_indexes.query_index(
                index_name=index_name,
                query_text=query_text,
                num_results=max(1, min(int(num_results), 50)),
            )
            payload = _jsonable(response)
            result = payload.get("result", {}) if isinstance(payload, dict) else {}
            rows = result.get("data_array", []) if isinstance(result, dict) else []
            return {
                "status": "ok",
                "resource": index_name,
                "operation": "vector_search",
                "row_count": len(rows),
                "result": payload,
            }
        except Exception as exc:
            return {
                "status": "unavailable",
                "resource": index_name,
                "operation": "vector_search",
                "error": str(exc),
            }
