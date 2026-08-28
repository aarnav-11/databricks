"""Dynamic, read-only adapter for the linked Ontobricks MCP App."""

from __future__ import annotations

import json
import os
import re
from typing import Any

from databricks.sdk import WorkspaceClient

READ_WORDS = ("query", "search", "find", "get", "read", "lookup", "retrieve", "inspect")
WRITE_WORDS = ("create", "write", "update", "delete", "remove", "insert", "upsert", "mutate", "set")


def _value(value: Any, key: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        return value.get(key, default)
    return getattr(value, key, default)


def _first_value(value: Any, *keys: str, default: Any = None) -> Any:
    for key in keys:
        result = _value(value, key)
        if result is not None:
            return result
    return default


def _decode_content(result: Any) -> Any:
    structured = _first_value(result, "structuredContent", "structured_content")
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
    return values[0] if len(values) == 1 else values


class MCPClientAdapter:
    """Discover MCP tools and call an explicitly safe read operation."""

    def __init__(
        self,
        workspace_client: WorkspaceClient | None = None,
        *,
        app_name: str | None = None,
        server_url: str | None = None,
        tool_name: str | None = None,
    ) -> None:
        self.workspace_client = workspace_client or WorkspaceClient()
        self.app_name = app_name if app_name is not None else os.getenv("MCP_APP_NAME", "")
        self.server_url = server_url or os.getenv("MCP_SERVER_URL")
        self.tool_name = tool_name if tool_name is not None else os.getenv("MCP_TOOL_NAME", "")
        self._client: Any = None

    def _resolve_server_url(self) -> str:
        if self.server_url:
            url = self.server_url.rstrip("/")
        else:
            if not self.app_name:
                raise RuntimeError("MCP_APP_NAME is not configured")
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

    def list_tools(self) -> dict[str, Any]:
        try:
            raw_tools = self._get_client().list_tools()
            tools = _value(raw_tools, "tools", raw_tools)
            normalized = []
            for tool in tools:
                normalized.append(
                    {
                        "name": str(_value(tool, "name", "")),
                        "description": str(_value(tool, "description", "")),
                        "input_schema": _first_value(tool, "inputSchema", "input_schema", default={}) or {},
                        "annotations": _value(tool, "annotations", {}) or {},
                    }
                )
            return {"status": "ok", "tools": normalized}
        except Exception as exc:
            return {"status": "unavailable", "tools": [], "error": str(exc)}

    @staticmethod
    def _is_auto_safe(tool: dict[str, Any]) -> bool:
        name = tool["name"].lower()
        tokens = set(re.findall(r"[a-z0-9]+", name))
        if any(word in tokens for word in WRITE_WORDS):
            return False
        annotations = tool.get("annotations") or {}
        read_only = _first_value(annotations, "readOnlyHint", "read_only_hint")
        return read_only is True or any(word in tokens for word in READ_WORDS)

    @staticmethod
    def _arguments(tool: dict[str, Any], question: str, claim_id: str) -> dict[str, Any] | None:
        schema = tool.get("input_schema") or {}
        properties = schema.get("properties", {}) if isinstance(schema, dict) else {}
        required = set(schema.get("required", [])) if isinstance(schema, dict) else set()
        arguments: dict[str, Any] = {}
        for name in properties:
            normalized = re.sub(r"[^a-z0-9]", "", name.lower())
            if normalized in {"claimid", "id", "entityid", "subjectid"}:
                arguments[name] = claim_id
            elif any(word in normalized for word in ("query", "question", "search", "text", "prompt", "input")):
                arguments[name] = question
            elif normalized in {"limit", "topk", "k", "numresults", "maxresults"}:
                arguments[name] = 10
        return arguments if required.issubset(arguments) else None

    def call(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        try:
            result = self._get_client().call_tool(tool_name, arguments)
            decoded = _decode_content(result)
            return {
                "status": "ok",
                "tool": tool_name,
                "operation": "mcp_tool",
                "result": decoded,
            }
        except Exception as exc:
            return {
                "status": "unavailable",
                "tool": tool_name,
                "operation": "mcp_tool",
                "error": str(exc),
            }

    def query(self, *, question: str, claim_id: str) -> dict[str, Any]:
        discovery = self.list_tools()
        if discovery["status"] != "ok":
            return {"resource": self.app_name, "operation": "mcp_tool_discovery", **discovery}

        tools = discovery["tools"]
        candidates = tools
        if self.tool_name:
            candidates = [tool for tool in tools if tool["name"] == self.tool_name]
            if not candidates:
                return {
                    "status": "unavailable",
                    "resource": self.app_name,
                    "operation": "mcp_tool_discovery",
                    "error": f"Configured MCP_TOOL_NAME {self.tool_name!r} was not found",
                    "available_tools": [tool["name"] for tool in tools],
                }
        else:
            candidates = [tool for tool in tools if self._is_auto_safe(tool)]
            candidates.sort(
                key=lambda tool: sum(
                    word in (tool["name"] + " " + tool["description"]).lower()
                    for word in ("claim", "fraud", "knowledge", "graph", "ontology")
                ),
                reverse=True,
            )

        for tool in candidates:
            arguments = self._arguments(tool, question, claim_id)
            if arguments is not None:
                result = self.call(tool["name"], arguments)
                result["resource"] = self.app_name
                result["arguments"] = arguments
                return result

        return {
            "status": "missing_configuration",
            "resource": self.app_name,
            "operation": "mcp_tool_discovery",
            "message": "No safe MCP read tool had an input schema this supervisor can populate.",
            "available_tools": [tool["name"] for tool in tools],
            "next_step": "Set MCP_TOOL_NAME after confirming the intended read-only tool.",
        }
