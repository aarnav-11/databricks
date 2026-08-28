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


def _mcp_error(decoded: Any) -> str | None:
    if isinstance(decoded, dict):
        errors = decoded.get("errors") or decoded.get("error")
        if errors:
            return str(errors)
    if isinstance(decoded, str) and "no domain selected" in decoded.casefold():
        return decoded
    return None


class MCPClientAdapter:
    """Discover MCP tools and call an explicitly safe read operation."""

    def __init__(
        self,
        workspace_client: WorkspaceClient | None = None,
        *,
        app_name: str | None = None,
        server_url: str | None = None,
        tool_name: str | None = None,
        domain_name: str | None = None,
    ) -> None:
        self.workspace_client = workspace_client or WorkspaceClient()
        self.app_name = app_name if app_name is not None else os.getenv("MCP_APP_NAME", "")
        self.server_url = server_url or os.getenv("MCP_SERVER_URL")
        self.tool_name = tool_name if tool_name is not None else os.getenv("MCP_TOOL_NAME", "")
        self.domain_name = (
            domain_name if domain_name is not None else os.getenv("MCP_DOMAIN_NAME", "")
        )
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
            error = _mcp_error(decoded)
            if _first_value(result, "isError", "is_error", default=False) or error:
                return {
                    "status": "unavailable",
                    "tool": tool_name,
                    "operation": "mcp_tool",
                    "error": error or "The MCP tool returned an error result.",
                    "result": decoded,
                }
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

    @staticmethod
    def _named_tool(tools: list[dict[str, Any]], expected_name: str) -> dict[str, Any] | None:
        expected = re.sub(r"[^a-z0-9]", "", expected_name.lower())
        for tool in tools:
            normalized = re.sub(r"[^a-z0-9]", "", tool["name"].lower())
            if normalized == expected or normalized.endswith(expected):
                return tool
        return None

    @staticmethod
    def _domain_records(value: Any) -> list[dict[str, Any]]:
        """Find domain records in the common MCP list_domains response shapes."""

        if isinstance(value, list):
            records: list[dict[str, Any]] = []
            for item in value:
                if isinstance(item, (str, int)):
                    records.append({"name": str(item)})
                else:
                    records.extend(MCPClientAdapter._domain_records(item))
            return records
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                return []
            try:
                parsed = json.loads(stripped)
            except json.JSONDecodeError:
                return []
            return MCPClientAdapter._domain_records(parsed)
        if not isinstance(value, dict):
            return []
        for key in (
            "domains",
            "available_domains",
            "domain_list",
            "items",
            "results",
            "result",
            "data",
        ):
            nested = value.get(key)
            if nested is not None:
                records = MCPClientAdapter._domain_records(nested)
                if records:
                    return records
        if any(key in value for key in ("domain_id", "domainId", "id", "name", "domain_name")):
            return [value]
        for key, nested in value.items():
            if "domain" in str(key).casefold():
                records = MCPClientAdapter._domain_records(nested)
                if records:
                    return records
        return []

    @staticmethod
    def _domain_text(record: dict[str, Any]) -> str:
        value = _first_value(
            record,
            "name",
            "domain_name",
            "display_name",
            "title",
            "id",
            "domain_id",
        )
        return str(value or "").strip()

    @staticmethod
    def _domain_search_text(record: dict[str, Any]) -> str:
        return " ".join(str(value) for value in record.values() if value is not None)

    def _choose_domain(self, records: list[dict[str, Any]]) -> dict[str, Any] | None:
        if self.domain_name:
            configured = self.domain_name.casefold()
            for record in records:
                values = {str(value).casefold() for value in record.values() if value is not None}
                if configured in values:
                    return record
            return {"name": self.domain_name, "domain_name": self.domain_name}
        if len(records) == 1:
            return records[0]
        claim_matches = [
            record
            for record in records
            if any(
                word in self._domain_search_text(record).casefold()
                for word in ("claim", "insurance", "fraud")
            )
        ]
        return claim_matches[0] if len(claim_matches) == 1 else None

    @staticmethod
    def _domain_arguments(tool: dict[str, Any], domain: dict[str, Any]) -> dict[str, Any] | None:
        schema = tool.get("input_schema") or {}
        properties = schema.get("properties", {}) if isinstance(schema, dict) else {}
        required = set(schema.get("required", [])) if isinstance(schema, dict) else set()
        domain_id = _first_value(domain, "domain_id", "domainId", "id")
        domain_name = _first_value(domain, "domain_name", "name", "display_name", "title")
        arguments: dict[str, Any] = {}
        for name in properties:
            normalized = re.sub(r"[^a-z0-9]", "", name.lower())
            if normalized in {"domainid", "id"} and domain_id is not None:
                arguments[name] = domain_id
            elif normalized in {"domain", "domainname", "name"} and domain_name is not None:
                arguments[name] = domain_name
        return arguments if required.issubset(arguments) else None

    def _initialize_domain(self, tools: list[dict[str, Any]]) -> dict[str, Any]:
        list_tool = self._named_tool(tools, "list_domains")
        select_tool = self._named_tool(tools, "select_domain")
        if not list_tool or not select_tool:
            return {
                "status": "not_required",
                "message": "This MCP server does not expose the Ontobricks domain handshake.",
            }

        listed = self.call(list_tool["name"], {})
        if listed["status"] != "ok":
            return {**listed, "operation": "mcp_list_domains"}

        records = self._domain_records(listed.get("result"))
        domain = self._choose_domain(records)
        if domain is None:
            message = (
                "Ontobricks returned domains but no unique claims domain could be selected."
                if records
                else "Ontobricks list_domains responded, but its domain records could not be parsed."
            )
            return {
                "status": "missing_configuration",
                "operation": "mcp_select_domain",
                "message": message,
                "available_domains": [self._domain_text(record) for record in records],
                "domain_discovery_result": listed.get("result"),
                "next_step": "Set MCP_DOMAIN_NAME to the exact claims-domain name from available_domains.",
            }

        arguments = self._domain_arguments(select_tool, domain)
        if arguments is None:
            return {
                "status": "missing_configuration",
                "operation": "mcp_select_domain",
                "message": "The select_domain input schema could not be populated.",
                "input_schema": select_tool.get("input_schema", {}),
                "selected_domain": self._domain_text(domain),
            }

        selected = self.call(select_tool["name"], arguments)
        selected["operation"] = "mcp_select_domain"
        selected["arguments"] = arguments
        return selected

    def query(self, *, question: str, claim_id: str) -> dict[str, Any]:
        discovery = self.list_tools()
        if discovery["status"] != "ok":
            return {"resource": self.app_name, "operation": "mcp_tool_discovery", **discovery}

        tools = discovery["tools"]
        domain_setup = self._initialize_domain(tools)
        if domain_setup["status"] not in {"ok", "not_required"}:
            domain_setup["resource"] = self.app_name
            return domain_setup

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
                if domain_setup["status"] == "ok":
                    result["domain_setup"] = {
                        "tool": domain_setup.get("tool"),
                        "arguments": domain_setup.get("arguments", {}),
                    }
                return result

        return {
            "status": "missing_configuration",
            "resource": self.app_name,
            "operation": "mcp_tool_discovery",
            "message": "No safe MCP read tool had an input schema this supervisor can populate.",
            "available_tools": [tool["name"] for tool in tools],
            "next_step": "Set MCP_TOOL_NAME after confirming the intended read-only tool.",
        }
