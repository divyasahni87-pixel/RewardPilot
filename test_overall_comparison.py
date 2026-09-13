"""Deterministic quoted-cost comparisons, independent of the model."""
import unittest
from unittest.mock import patch

import decision_engine as engine


class OverallComparisonTests(unittest.TestCase):
    def test_exact_450_cash_4500_miles_structured_object(self):
        cash = engine.compare_cash_cards(
            ["delta_platinum_amex", "amex_gold", "chase_sapphire_preferred"], 450,
            {"type": "flight", "merchant": "Delta", "booking_channel": "direct"})
        award = engine.evaluate_award_option("Delta SkyMiles", 4500, 10, 450,
                                             {"Delta SkyMiles": 50000, "Amex Membership Rewards": 70000})
        result = engine.compare_payment_options(cash, award)
        self.assertEqual(cash[0]["card_id"], "amex_gold")
        self.assertEqual({key: result[key] for key in (
            "cash_effective_cost", "points_effective_cost", "overall_winner", "estimated_advantage_usd")},
            {"cash_effective_cost": 429.75, "points_effective_cost": 64.0,
             "overall_winner": "points", "estimated_advantage_usd": 365.75})

    def compare(self, points, **kwargs):
        cash = engine.compare_cash_cards(
            ["amex_gold", "delta_platinum_amex", "chase_sapphire_preferred"], 500,
            {"type": "flight", "merchant": "Delta", "booking_channel": "direct"})
        award = engine.evaluate_award_option("Delta SkyMiles", points, 10, 500,
                                             {"Delta SkyMiles": 50000, "Amex Membership Rewards": 70000})
        return engine.compare_payment_options(cash, award, **kwargs)

    def test_450_miles_clearly_wins(self):
        result = self.compare(450)
        self.assertEqual(result["cash_effective_cost"], 477.5)
        self.assertEqual(result["points_effective_cost"], 15.4)
        self.assertEqual(result["overall_winner"], "points")
        self.assertEqual(result["estimated_advantage_usd"], 462.1)
        self.assertEqual(result["reason_code"], "clear_points_advantage")

    def test_45000_miles_uses_configured_valuation(self):
        result = self.compare(45000)
        self.assertEqual(result["points_effective_cost"], 550)
        self.assertEqual(result["overall_winner"], "cash")
        self.assertEqual(result["estimated_advantage_usd"], 72.5)
        self.assertEqual(result["reason_code"], "clear_cash_advantage")
        with patch.dict(engine.REWARD_VALUATIONS, {"Delta SkyMiles": {"cents_per_point": 0.5}}):
            self.assertEqual(self.compare(45000)["overall_winner"], "points")

    def test_cash_only(self):
        self.assertIsNone(engine.compare_payment_options([], None))

    def test_missing_award_or_cash_valuation(self):
        for program in ("Delta SkyMiles", "Amex Membership Rewards"):
            with self.subTest(program=program), patch.dict(engine.REWARD_VALUATIONS, {program: {}}):
                result = self.compare(450)
                self.assertEqual(result["status"], "insufficient_data")
                self.assertIsNone(result["estimated_advantage_usd"])
                self.assertIn("valuation is missing", result["reason"])

    def test_close_call_and_tie(self):
        self.assertEqual(self.compare(39000)["status"], "close_call")
        with patch.dict(engine.REWARD_VALUATIONS, {"Delta SkyMiles": {"cents_per_point": 1}}):
            result = self.compare(46750)
            self.assertEqual(result["status"], "close_call")
            self.assertEqual(result["estimated_advantage_usd"], 0)

    def test_incomplete_assumptions(self):
        self.assertEqual(self.compare(450, booking_channel_known=False)["status"], "conditional_winner")
        result = self.compare(90000)
        self.assertEqual(result["status"], "conditional_winner")
        self.assertTrue(result["conditions"])

    def test_transfer_values_actual_consumed_currencies(self):
        result = self.compare(90000)
        self.assertEqual(result["points_opportunity_cost"], 1200)
        self.assertEqual(result["valuation_assumptions"]["Delta SkyMiles"]["points_consumed"], 50000)
        self.assertEqual(result["valuation_assumptions"]["Amex Membership Rewards"]["points_consumed"], 40000)
        self.assertEqual(result["status"], "conditional_winner")
        self.assertIsNone(result["overall_winner"])

    def test_multiple_transfer_paths_are_not_chosen_arbitrarily(self):
        award = engine.evaluate_award_option("Marriott Bonvoy", 90000, 10, 1500,
            {"Marriott Bonvoy": 50000, "Amex Membership Rewards": 70000,
             "Chase Ultimate Rewards": 85000})
        cash = engine.compare_cash_cards(["amex_gold"], 1500,
            {"type": "flight", "merchant": "Delta", "booking_channel": "direct"})
        result = engine.compare_payment_options(cash, award)
        self.assertEqual(result["status"], "insufficient_data")
        self.assertIsNone(result["points_opportunity_cost"])
        self.assertIsNone(result["overall_winner"])
        self.assertEqual(result["reason_code"], "multiple_transfer_paths")

    def test_requested_transfer_close_call(self):
        cash = engine.compare_cash_cards(["amex_gold"], 823.01,
            {"type": "flight", "merchant": "Delta", "booking_channel": "direct"})
        award = engine.evaluate_award_option("Delta SkyMiles", 60000, 10, 823.01,
            {"Delta SkyMiles": 50000, "Amex Membership Rewards": 70000})
        result = engine.compare_payment_options(cash, award)
        self.assertEqual(result["status"], "close_call")
        self.assertEqual(result["leading_option"], "points")
        self.assertEqual(result["cash_effective_cost"], 785.97)
        self.assertEqual(result["points_effective_cost"], 766)
        self.assertEqual(result["transfer_fee_usd"], 6)
        self.assertEqual(result["estimated_advantage_usd"], 19.97)
        self.assertEqual(result["reason_code"], "close_call_points")
        self.assertNotEqual(result["status"], "insufficient_data")
        self.assertEqual(result["selected_transfer"]["required_transfer"], 10000)
        self.assertEqual(result["missing_fields"], [])
        self.assertTrue(result["conditions"])
        with patch.dict(engine.COMPARISON_SETTINGS, {"close_call_fraction": 0.01}):
            self.assertEqual(engine.compare_payment_options(cash, award)["status"], "conditional_winner")

    def test_missing_source_valuation_and_insufficient_balance_diagnostics(self):
        cash = engine.compare_cash_cards(["delta_platinum_amex"], 1500,
            {"type": "flight", "merchant": "Delta", "booking_channel": "direct"})
        award = engine.evaluate_award_option("Delta SkyMiles", 60000, 10, 1500,
            {"Delta SkyMiles": 50000, "Amex Membership Rewards": 70000})
        result = engine.compare_payment_options(cash, award)
        self.assertEqual(result["status"], "conditional_winner")
        self.assertEqual(result["reason_code"], "conditional_points_advantage")
        with patch.dict(engine.REWARD_VALUATIONS, {"Amex Membership Rewards": {}}):
            result = engine.compare_payment_options(cash, award)
            self.assertEqual(result["reason_code"], "missing_reward_valuation")
            self.assertEqual(result["missing_fields"], ["valuation:Amex Membership Rewards"])
        award = engine.evaluate_award_option("Delta SkyMiles", 60000, 10, 1500,
            {"Delta SkyMiles": 50000, "Amex Membership Rewards": 9000})
        result = engine.compare_payment_options(cash, award)
        self.assertEqual(result["reason_code"], "no_feasible_transfer")
        self.assertIsNone(result["selected_transfer"])
        del award["taxes_fees"]
        result = engine.compare_payment_options(cash, award)
        self.assertEqual(result["reason_code"], "missing_award_data")
        self.assertEqual(result["missing_fields"], ["taxes_fees"])

    def test_close_call_both_leads(self):
        self.assertEqual(self.compare(38000)["leading_option"], "points")
        self.assertEqual(self.compare(38000)["status"], "close_call")
        self.assertEqual(self.compare(39000)["leading_option"], "cash")
        self.assertEqual(self.compare(39000)["status"], "close_call")

    def test_known_fee_cap_and_unknown_fee(self):
        cash = engine.compare_cash_cards(["amex_gold"], 5000,
            {"type": "flight", "merchant": "Delta", "booking_channel": "direct"})
        award = engine.evaluate_award_option("Delta SkyMiles", 200000, 10, 5000,
            {"Amex Membership Rewards": 200000})
        result = engine.compare_payment_options(cash, award)
        self.assertEqual(result["transfer_fee_usd"], 99)
        self.assertEqual(result["status"], "conditional_winner")
        award = engine.evaluate_award_option("Marriott Bonvoy", 20000, 10, 5000,
            {"Chase Ultimate Rewards": 20000})
        result = engine.compare_payment_options(cash, award)
        self.assertIsNone(result["transfer_fee_usd"])
        self.assertEqual(result["status"], "conditional_winner")
        self.assertIn("unconfirmed", " ".join(result["conditions"]))


if __name__ == "__main__":
    unittest.main(verbosity=2)
