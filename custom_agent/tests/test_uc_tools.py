import sys
import types
import unittest

try:
    from databricks.sdk import WorkspaceClient  # noqa: F401
    from databricks.sdk.service.sql import StatementParameterListItem  # noqa: F401
except (ImportError, ModuleNotFoundError):
    databricks_module = sys.modules.setdefault("databricks", types.ModuleType("databricks"))
    sdk_module = sys.modules.setdefault("databricks.sdk", types.ModuleType("databricks.sdk"))
    service_module = sys.modules.setdefault(
        "databricks.sdk.service", types.ModuleType("databricks.sdk.service")
    )
    sql_module = types.ModuleType("databricks.sdk.service.sql")

    class StatementParameterListItem:
        def __init__(self, *, name, value):
            self.name = name
            self.value = value

    sdk_module.WorkspaceClient = object
    sql_module.StatementParameterListItem = StatementParameterListItem
    service_module.sql = sql_module
    sdk_module.service = service_module
    databricks_module.sdk = sdk_module
    sys.modules["databricks.sdk.service.sql"] = sql_module

from server.uc_tools import UCTableClient


class FakeTables:
    def __init__(self, columns):
        self.columns = columns

    def get(self, *, full_name):
        return {"columns": [{"name": name} for name in self.columns]}


class FakeStatementExecution:
    def __init__(self):
        self.last_request = None

    def execute_statement(self, **kwargs):
        self.last_request = kwargs
        return {
            "status": {"state": "SUCCEEDED"},
            "manifest": {"schema": {"columns": [{"name": "claim_id"}]}},
            "result": {"data_array": [["CLM-0038533"]]},
        }


class FakeWorkspace:
    def __init__(self, columns):
        self.tables = FakeTables(columns)
        self.statement_execution = FakeStatementExecution()


class UCTableClientTests(unittest.TestCase):
    def test_metric_view_wraps_each_measure(self):
        workspace = FakeWorkspace(["claim_id", "siu_referral_rate", "avg_fraud_score"])
        client = UCTableClient(workspace_client=workspace, warehouse_id="warehouse")

        result = client.query_metric_for_claim(
            table_name="catalog.schema.claim_fraud_metrics",
            claim_id="CLM-0038533",
            lookup_columns=("claim_id",),
            measure_columns=("siu_referral_rate", "avg_fraud_score"),
        )

        statement = workspace.statement_execution.last_request["statement"]
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["operation"], "query_metric_view")
        self.assertIn("MEASURE(`siu_referral_rate`)", statement)
        self.assertIn("MEASURE(`avg_fraud_score`)", statement)
        self.assertNotIn("SELECT *", statement)
        self.assertIn("GROUP BY `claim_id`", statement)

    def test_policy_number_is_taken_from_previous_claim_evidence(self):
        workspace = FakeWorkspace(["policy_id", "policy_number"])
        client = UCTableClient(workspace_client=workspace, warehouse_id="warehouse")

        result = client.query_for_claim(
            table_name="catalog.schema.policy_360",
            claim_id="CLM-0038533",
            evidence={"claim_profile": {"rows": [{"policy_number": "POL-0012495"}]}},
            lookup_columns=("policy_id", "policy_number", "claim_id"),
        )

        self.assertEqual(result["lookup_column"], "policy_number")
        self.assertEqual(result["lookup_values"], ["POL-0012495"])

    def test_claim_number_alias_uses_the_requested_claim_id(self):
        workspace = FakeWorkspace(["claim_number", "party_id"])
        client = UCTableClient(workspace_client=workspace, warehouse_id="warehouse")

        result = client.query_for_claim(
            table_name="catalog.schema.party_360",
            claim_id="CLM-0038533",
            evidence={},
            lookup_columns=("party_id", "claim_id", "claim_number"),
        )

        self.assertEqual(result["lookup_column"], "claim_number")
        self.assertEqual(result["lookup_values"], ["CLM-0038533"])


if __name__ == "__main__":
    unittest.main()
