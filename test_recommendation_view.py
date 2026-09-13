import unittest
from recommendation_view import format_recommendation


class RecommendationTests(unittest.TestCase):
    def report(self):
        return {"inputs": {"booking_channel": "direct", "compare_points": True,
                           "discount_status": "I'm not sure"},
                "cash": [{"card_name": "Owned card", "reward_amount": 1234,
                          "reward_program": "Reward currency", "reward_value": {"estimated_value_usd": 19.87}}],
                "award": {"required_points": 90000, "target_program": "Delta SkyMiles", "taxes_fees": 33.6,
                          "existing_points": 50000, "shortfall": 40000, "cents_per_point": 1.63,
                          "transfer_options": [{"from_program": "Amex Membership Rewards", "required_transfer": 40000,
                                                "ratio": "1000:1000", "can_cover_shortfall": True}]},
                "policy_search_called": True,
                "evidence": [{"text": "- Transfers are final.", "title": "Retrieved policy", "last_verified": "2026-09-12"}]}

    def test_structured_values_and_conditions_are_preserved(self):
        answer = format_recommendation(self.report())
        for value in ("$19.87", "1,234 Reward currency", "90,000", "$33.60", "50,000", "40,000", "1.63¢",
                      "Transfers are final.", "Retrieved policy", "BEST POINTS OPTION"):
            self.assertIn(value, answer)

    def test_no_policy_section_without_actual_lookup(self):
        report = self.report()
        report["policy_search_called"] = False
        self.assertNotIn("IMPORTANT CONDITIONS", format_recommendation(report))

    def test_cash_only_does_not_leak_unsolicited_award_data(self):
        report = self.report()
        report["inputs"]["compare_points"] = False
        answer = format_recommendation(report)
        self.assertIn("$19.87", answer)
        for text in ("BEST POINTS", "IMPORTANT CONDITIONS", "transfer", "compare_points"):
            self.assertNotIn(text.lower(), answer.lower())


if __name__ == "__main__":
    unittest.main()
