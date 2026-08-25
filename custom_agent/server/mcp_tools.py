"""Adapter for the existing Databricks-hosted MCP App."""

from __future__ import annotations

import json
import os
from typing import Any

from databricks.sdk import WorkspaceClient


def _value(value: Any, key: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        return value.get(key, default)
    return getattr(value, key, default)


def _decode_content(result: Any) -> Any:
    """Convert MCP text content into a JSON value when the server returned one."""

    structured = _value(result, "structuredContent")
    if structured is not None:
        return structured

    content = _value(result, "content")
    if content is None:
        return result

    values: list[Any] = []
    for block in content:
        text = _value(block, "text")
        if text is None:
            values.append(block)
            continue
        try:
            values.append(json.loads(text))
        except (TypeError, json.JSONDecodeError):
            values.append(text)
    if len(values) == 1:
        return values[0]
    return values


class MCPClientAdapter:
    """Call only the read-only VIN tool from the POC MCP server."""

    def __init__(
        self,
        workspace_client: WorkspaceClient | None = None,
        *,
        app_name: str | None = None,
        server_url: str | None = None,
    ) -> None:
        self.workspace_client = workspace_client or WorkspaceClient()
        self.app_name = app_name or os.getenv("MCP_APP_NAME", "mcp-insurance-fraud-poc")
        self.server_url = server_url or os.getenv("MCP_SERVER_URL")
        self._client: Any = None

    def _resolve_server_url(self) -> str:
        if self.server_url:
            url = self.server_url.rstrip("/")
        else:
            app = self.workspace_client.apps.get(name=self.app_name)
            url = _value(app, "url")
            if not url:
                raise RuntimeError(f"Databricks App {self.app_name!r} has no URL")
            url = str(url).rstrip("/")
        return url if url.endswith("/mcp") else f"{url}/mcp"

    def _get_client(self) -> Any:
        if self._client is None:
            from databricks_mcp import DatabricksMCPClient

            self._client = DatabricksMCPClient(
                server_url=self._resolve_server_url(),
                workspace_client=self.workspace_client,
            )
        return self._client

    def call(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        try:
            result = self._get_client().call_tool(tool_name, arguments)
            decoded = _decode_content(result)
            if isinstance(decoded, dict):
                return {"status": "ok", "tool": tool_name, **decoded}
            return {"status": "ok", "tool": tool_name, "result": decoded}
        except Exception as exc:  # MCP availability must not crash the loop.
            return {
                "status": "unavailable",
                "tool": tool_name,
                "error": str(exc),
            }

    def decode_vin(self, vin: str) -> dict[str, Any]:
        return self.call("decode_vin", {"vin": vin})
