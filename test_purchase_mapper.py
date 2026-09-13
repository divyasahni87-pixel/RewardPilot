"""Booking-channel regression coverage using the existing catalog and engine."""

import unittest

from decision_engine import compare_cash_cards
from purchase_mapper import map_purchase_to_card_category
from recommendation_view import format_recommendation

CARDS = ["delta_platinum_amex", "amex_gold", "chase_sapphire_preferred"]


class BookingChannelTests(unittest.TestCase):
    def check_channel(self, channel, expected):
        rows = compare_cash_cards(CARDS, 1250, {
            "type": "flight", "merchant": "Delta", "booking_channel": channel})
        actual = {r["card_id"]: (r["mapped_category"], r["earn_rate"], r["reward_amount"],
                                r["reward_value"]["estimated_value_usd"]) for r in rows}
        self.assertEqual(actual, dict(zip(CARDS, expected)))
        return rows

    def test_direct_airline(self):
        self.check_channel("direct", [
            ("delta_purchase", 3, 3750, 45),
            ("flight_direct_or_amex_travel", 3, 3750, 56.25),
            ("travel_other", 2, 2500, 37.50)])

    def test_chase_travel_and_public_recommendation(self):
        rows = self.check_channel("chase_travel", [
            ("other", 1, 1250, 15), ("other", 1, 1250, 18.75),
            ("chase_travel", 5, 6250, 93.75)])
        self.assertEqual(rows[0]["card_id"], "chase_sapphire_preferred")
        answer = format_recommendation({"cash": rows, "award": None,
            "inputs": {"booking_channel": "chase_travel", "compare_points": False}})
        self.assertIn("Chase Sapphire Preferred", answer)
        self.assertIn("$93.75", answer)
        self.assertIn("Booking channel: Chase Travel", answer)
        self.assertNotIn("direct", answer.lower())

    def test_amex_travel(self):
        self.check_channel("amex_travel", [
            ("other", 1, 1250, 15),
            ("flight_direct_or_amex_travel", 3, 3750, 56.25),
            ("travel_other", 2, 2500, 37.50)])

    def test_unknown_channel(self):
        for channel in ("", None, "unknown"):
            with self.subTest(channel=channel):
                self.check_channel(channel, [
                    ("other", 1, 1250, 15), ("other", 1, 1250, 18.75),
                    ("travel_other", 2, 2500, 37.50)])
        purchase = {"type": "flight", "merchant": "Delta"}
        self.assertEqual(map_purchase_to_card_category(CARDS[0], purchase), "other")

    def test_non_delta_direct_flight_does_not_get_delta_bonus(self):
        self.assertEqual(map_purchase_to_card_category(CARDS[0], {
            "type": "flight", "merchant": "United", "booking_channel": "direct"}), "other")


if __name__ == "__main__":
    unittest.main(verbosity=2)
