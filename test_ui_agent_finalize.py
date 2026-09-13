"""Contract checks for the public structured-report finalizer."""
from copy import deepcopy
import unittest
from unittest.mock import patch

import ui_agent
from decision_engine import compare_cash_cards, evaluate_award_option


class FinalizeComparisonTests(unittest.TestCase):
    def report(self):
        return {"inputs": {"compare_points": True, "booking_channel": "direct"},
                "cash": compare_cash_cards(["amex_gold"], 450,
                    {"type": "flight", "merchant": "Delta", "booking_channel": "direct"}),
                "award": evaluate_award_option("Delta SkyMiles", 4500, 10, 450,
                    {"Delta SkyMiles": 50000}), "answer": "Preserve existing prose"}

    def test_exact_scenario_preserves_inputs_and_attaches_engine_result(self):
        report = self.report()
        before = deepcopy(report)
        self.assertTrue(callable(ui_agent.finalize_comparison))
        self.assertIs(ui_agent.finalize_comparison(report), report)
        for key in before:
            self.assertEqual(report[key], before[key])
        overall = report["overall_comparison"]
        self.assertEqual(overall["overall_winner"], "points")
        self.assertEqual(overall["cash_effective_cost"], 429.75)
        self.assertEqual(overall["points_effective_cost"], 64)
        self.assertEqual(overall["estimated_advantage_usd"], 365.75)

    def test_no_points_returns_report_unchanged(self):
        for field in ("disabled", "award", "cash"):
            report = self.report()
            if field == "disabled":
                report["inputs"]["compare_points"] = False
            else:
                report[field] = None
            before = deepcopy(report)
            with patch("decision_engine.compare_payment_options") as compare:
                self.assertIs(ui_agent.finalize_comparison(report), report)
                compare.assert_not_called()
            self.assertEqual(report, before)


if __name__ == "__main__":
    unittest.main()
