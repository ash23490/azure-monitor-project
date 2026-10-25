"""Offline smoke tests. These cannot validate KQL parsing or Azure deployment."""
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class BundleTests(unittest.TestCase):
    def test_arm_is_real_resource_template(self):
        doc = json.loads((ROOT / "arm-templates/main.json").read_text(encoding="utf-8"))
        self.assertTrue(doc["$schema"].endswith("deploymentTemplate.json#"))
        self.assertEqual(len(doc["resources"]), 4)
        self.assertEqual(doc["parameters"]["deployCostAlert"]["defaultValue"], False)
        types = {x["type"] for x in doc["resources"]}
        self.assertIn("Microsoft.OperationalInsights/workspaces", types)
        self.assertIn("Microsoft.Insights/scheduledQueryRules", types)

    def test_no_hardcoded_shared_key_or_legacy_log_api(self):
        ps = (ROOT / "scripts/Generate-CostData.ps1").read_text(encoding="utf-8")
        self.assertNotIn("$WorkspaceKey =", ps)
        self.assertNotIn("ods.opinsights.azure.com", ps)
        self.assertIn("dataCollectionRules/", ps)
        self.assertIn("get-access-token", ps)

    def test_kql_removed_known_antipatterns(self):
        kql = (ROOT / "kusto-queries/cost-anomaly-detection.kql").read_text(encoding="utf-8")
        self.assertNotIn("| | extend", kql)
        self.assertNotIn("sum(ContainerRestartCount)", kql)
        self.assertNotIn("where IsAnomaly_b ==", kql)
        self.assertIn("datetime_utc_to_local", kql)
        self.assertIn("PreviousSpend", kql)
        self.assertIn("BaselineDays >= 7", kql)

    def test_example_spike_detection_math(self):
        # Illustrates the same 30% / 5.0 dual-threshold design, independently.
        costs = [40.0] * 20 + [100.0] + [40.0] * 9
        flagged = []
        for day_index, amount in enumerate(costs):
            past = costs[max(0, day_index - 29):day_index]
            if len(past) < 7:
                continue
            avg = sum(past) / len(past)
            if (amount-avg) > 5.0 and (amount-avg)/avg > 0.30:
                flagged.append(day_index)
        self.assertEqual(flagged, [20])


if __name__ == "__main__":
    unittest.main()
