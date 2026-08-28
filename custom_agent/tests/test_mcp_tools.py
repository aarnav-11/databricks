import sys
import types
import unittest

try:
    from databricks.sdk import WorkspaceClient  # noqa: F401
except ModuleNotFoundError:
    databricks_module = types.ModuleType("databricks")
    sdk_module = types.ModuleType("databricks.sdk")
    sdk_module.WorkspaceClient = object
    databricks_module.sdk = sdk_module
    sys.modules["databricks"] = databricks_module
    sys.modules["databricks.sdk"] = sdk_module

from server.mcp_tools import MCPClientAdapter


class FakeMCPAdapter(MCPClientAdapter):
    def __init__(self, *, domains, domain_name=""):
        super().__init__(workspace_client=object(), app_name="ontobricks", domain_name=domain_name)
        self.domains = domains
        self.calls = []

    def list_tools(self):
        return {
            "status": "ok",
            "tools": [
                {"name": "list_domains", "description": "", "input_schema": {}, "annotations": {}},
                {
                    "name": "select_domain",
                    "description": "",
                    "input_schema": {
                        "properties": {"domain_name": {"type": "string"}},
                        "required": ["domain_name"],
                    },
                    "annotations": {},
                },
                {
                    "name": "search_claim",
                    "description": "Read claim graph",
                    "input_schema": {
                        "properties": {"claim_id": {"type": "string"}},
                        "required": ["claim_id"],
                    },
                    "annotations": {"readOnlyHint": True},
                },
            ],
        }

    def call(self, tool_name, arguments):
        self.calls.append((tool_name, arguments))
        if tool_name == "list_domains":
            return {"status": "ok", "tool": tool_name, "result": {"domains": self.domains}}
        return {"status": "ok", "tool": tool_name, "result": {"called": tool_name}}


class MCPDomainInitializationTests(unittest.TestCase):
    def test_initializes_claim_domain_before_querying_graph(self):
        adapter = FakeMCPAdapter(domains=[{"name": "Claims Knowledge Graph"}])

        result = adapter.query(question="Review CLM-1001", claim_id="CLM-1001")

        self.assertEqual(result["status"], "ok")
        self.assertEqual(
            adapter.calls,
            [
                ("list_domains", {}),
                ("select_domain", {"domain_name": "Claims Knowledge Graph"}),
                ("search_claim", {"claim_id": "CLM-1001"}),
            ],
        )

    def test_requires_configuration_when_multiple_domains_are_ambiguous(self):
        adapter = FakeMCPAdapter(domains=[{"name": "Property"}, {"name": "Automotive"}])

        result = adapter.query(question="Review CLM-1001", claim_id="CLM-1001")

        self.assertEqual(result["status"], "missing_configuration")
        self.assertEqual(result["operation"], "mcp_select_domain")
        self.assertEqual(adapter.calls, [("list_domains", {})])

    def test_configured_domain_selects_one_of_multiple_domains(self):
        adapter = FakeMCPAdapter(
            domains=[{"name": "Property"}, {"name": "Automotive"}],
            domain_name="Automotive",
        )

        result = adapter.query(question="Review CLM-1001", claim_id="CLM-1001")

        self.assertEqual(result["status"], "ok")
        self.assertEqual(adapter.calls[1], ("select_domain", {"domain_name": "Automotive"}))

    def test_mcp_error_result_is_not_reported_as_success(self):
        class ErrorClient:
            @staticmethod
            def call_tool(tool_name, arguments):
                return {
                    "isError": True,
                    "content": [{"text": "No domain selected"}],
                }

        adapter = MCPClientAdapter(workspace_client=object(), app_name="ontobricks")
        adapter._client = ErrorClient()

        result = adapter.call("query_graphql", {"query": "claim"})

        self.assertEqual(result["status"], "unavailable")
        self.assertIn("No domain selected", result["error"])


if __name__ == "__main__":
    unittest.main()
