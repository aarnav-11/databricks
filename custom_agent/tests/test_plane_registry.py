import json
import os
import unittest
from pathlib import Path
from unittest.mock import patch

from server.plane_registry import extract_claim_id, load_plane_specs, validate_planes


class PlaneRegistryTests(unittest.TestCase):
    def test_app_yaml_binds_every_current_resource_key(self):
        app_yaml = (Path(__file__).parents[1] / "app.yaml").read_text()

        self.assertIn("valueFrom: sql-warehouse", app_yaml)
        for key in (
            "ontobricks_kg",
            "claim_360",
            "party_360",
            "location_360",
            "policy_360",
            "LLM",
            "vector-search-index",
            "claim_fraud_metrics",
        ):
            self.assertIn(f"valueFrom: {key}", app_yaml)
        self.assertIn(
            "value: chunk_id,chunk_to_retrieve,source_path,document_type",
            app_yaml,
        )
        self.assertIn("value: chunk_to_embed", app_yaml)

    def test_defaults_match_linked_app_resources(self):
        specs = load_plane_specs("")

        self.assertEqual(
            {spec.env_var for spec in specs.values()},
            {
                "CLAIM_TABLE",
                "PARTY_TABLE",
                "LOCATION_TABLE",
                "POLICY_TABLE",
                "CLAIM_FRAUD_METRICS_TABLE",
                "VECTOR_SEARCH_INDEX",
                "MCP_APP_NAME",
            },
        )
        self.assertEqual(
            {spec.name for spec in specs.values() if spec.mandatory},
            {"claim_profile", "fraud_metrics"},
        )

    def test_json_configuration_adds_a_plane_without_python_changes(self):
        config = json.dumps(
            {
                "planes": [
                    {
                        "name": "provider_profile",
                        "description": "Provider facts.",
                        "kind": "table",
                        "env_var": "PROVIDER_TABLE",
                        "lookup_columns": ["provider_id"],
                    }
                ]
            }
        )

        specs = load_plane_specs(config)

        self.assertEqual(specs["provider_profile"].env_var, "PROVIDER_TABLE")
        self.assertEqual(specs["provider_profile"].lookup_columns, ("provider_id",))

    def test_validation_inserts_only_registered_mandatory_planes(self):
        specs = load_plane_specs("")

        result = validate_planes(
            ["document_search", "made_up_plane"],
            already_queried=[],
            total_queried=0,
            claim_id="CLM-1001",
            evidence={},
            user_text="summarize CLM-1001",
            plane_specs=specs,
        )

        self.assertEqual(
            result.accepted,
            ("claim_profile", "fraud_metrics", "document_search"),
        )
        self.assertEqual(result.rejected, ("made_up_plane",))

    def test_claim_id_pattern_can_be_changed_for_another_workspace(self):
        with patch.dict(os.environ, {"CLAIM_ID_REGEX": r"\bAZ-([0-9]{3})\b"}):
            self.assertEqual(extract_claim_id("Review AZ-417"), "417")


if __name__ == "__main__":
    unittest.main()
