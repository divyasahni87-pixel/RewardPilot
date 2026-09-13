"""Catalog-backed purchase mappings and adaptive UI regressions."""
import unittest
from unittest.mock import patch

import agent_tools
import ui_agent
from decision_engine import compare_cash_cards, get_card, get_reward_value
from test_app import offline_run
from streamlit.testing.v1 import AppTest


class PurchaseTypeTests(unittest.TestCase):
    def test_catalog_categories_and_values(self):
        cases = [
            ({"type": "hotel", "merchant": "Marriott", "booking_channel": "direct"},
             {"delta_platinum_amex": "hotel_direct", "amex_gold": "other", "chase_sapphire_preferred": "travel_other", "marriott_boundless": "marriott"}),
            ({"type": "hotel", "merchant": "Marriott", "booking_channel": "chase_travel"},
             {"delta_platinum_amex": "other", "amex_gold": "other", "chase_sapphire_preferred": "chase_travel"}),
            ({"type": "hotel", "merchant": "Marriott", "booking_channel": "amex_travel", "prepaid": True},
             {"amex_gold": "amex_travel_prepaid_hotel", "amex_platinum": "amex_travel_prepaid_hotel", "delta_platinum_amex": "other"}),
            ({"type": "hotel", "merchant": "Hotel", "booking_channel": "amex_travel"}, {"amex_gold": "other"}),
            ({"type": "groceries", "merchant": "Eligible supermarket", "purchase_method": "in_store", "is_us_supermarket": True},
             {"amex_gold": "us_supermarket", "chase_sapphire_preferred": "other"}),
            ({"type": "groceries", "merchant": "Eligible supermarket", "purchase_method": "online", "online_grocery_eligible": True, "is_us_supermarket": True},
             {"amex_gold": "us_supermarket", "chase_sapphire_preferred": "online_grocery"}),
            ({"type": "groceries", "merchant": "Whole Foods", "purchase_method": "in_store", "prime_member": True}, {"prime_visa": "whole_foods"}),
            ({"type": "restaurant", "merchant": "Restaurant"},
             {"amex_gold": "restaurant", "chase_sapphire_preferred": "dining", "delta_platinum_amex": "restaurant", "marriott_boundless": "grocery_gas_dining_combined"}),
            ({"type": "amazon", "merchant": "Amazon", "prime_member": True}, {"prime_visa": "amazon", "amex_gold": "other"}),
            ({"type": "amazon", "merchant": "Amazon"}, {"prime_visa": "other"}),
            ({"type": "groceries", "merchant": "Unknown"}, {"amex_gold": "other", "chase_sapphire_preferred": "other"}),
            ({"type": "groceries", "merchant": "Walmart", "purchase_method": "online", "is_us_supermarket": True, "online_grocery_eligible": True},
             {"amex_gold": "other", "chase_sapphire_preferred": "other"}),
        ]
        for purchase, expected in cases:
            with self.subTest(purchase=purchase):
                rows = compare_cash_cards(list(expected), 250, purchase)
                self.assertEqual({row["card_id"] for row in rows}, set(expected))
                for row in rows:
                    card = get_card(row["card_id"])
                    rule = next(rule for rule in card["earn_rules"] if rule["category"] == expected[row["card_id"]])
                    amount = 250 * rule["rate"] / (100 if rule["unit"] == "percent_cashback" else 1)
                    value = amount if rule["unit"] == "percent_cashback" else get_reward_value(card["reward_program"], amount)["estimated_value_usd"]
                    self.assertEqual(row["mapped_category"], rule["category"])
                    self.assertEqual(row["earn_rate"], rule["rate"])
                    self.assertEqual(row["reward_amount"], amount)
                    self.assertEqual(row["reward_value"]["estimated_value_usd"], value)

    def test_tool_passes_purchase_details(self):
        with patch.object(agent_tools, "get_user_cards", return_value=["amex_gold"]):
            rows = agent_tools.compare_cash_payment.invoke({"user_id": 1, "purchase_type": "hotel", "merchant": "Hotel",
                "amount": 250, "booking_channel": "amex_travel", "prepaid": True})
            self.assertEqual(rows[0]["mapped_category"], "amex_travel_prepaid_hotel")

    def test_hotel_award_ui(self):
        with patch.object(ui_agent, "run_analysis", side_effect=offline_run):
            app = AppTest.from_file("app.py", default_timeout=40).run()
            app.selectbox(key="purchase_type").select("Hotel").run()
            app.text_input(key="merchant").set_value("Marriott").run()
            app.toggle(key="compare_points").set_value(True).run()
            app.selectbox(key="target_program").select("Marriott Bonvoy").run()
            app.number_input(key="required_points").set_value(40000).run()
            app.number_input(key="taxes_fees").set_value(10.0).run()
            app.button(key="find").click().run()
            self.assertFalse(app.exception)
            report = app.session_state["analysis"]
            self.assertEqual(report["award"]["target_program"], "Marriott Bonvoy")
            self.assertIn("Direct with hotel", report["answer"])
            self.assertNotIn("airline", report["answer"])
            self.assertIn("40,000 points + $10.00", [item.value for item in app.markdown])

    def test_adaptive_ui_and_no_stale_flight_requests(self):
        for kind in ("Hotel", "Groceries", "Restaurant", "Amazon"):
            with self.subTest(kind=kind), patch.object(ui_agent, "run_analysis", side_effect=offline_run):
                app = AppTest.from_file("app.py", default_timeout=40).run()
                app.button(key="example").click().run()
                app.selectbox(key="purchase_type").select(kind).run()
                self.assertFalse(app.exception)
                self.assertIsNone(app.session_state["analysis"])
                self.assertNotIn("required_points", [item.key for item in app.number_input])
                if kind == "Hotel":
                    self.assertFalse(app.toggle(key="compare_points").value)
                    self.assertEqual(app.selectbox(key="channel").value, "Direct with hotel")
                    app.toggle(key="compare_points").set_value(True).run()
                    self.assertIsNone(app.number_input(key="required_points").value)
                    app.toggle(key="compare_points").set_value(False).run()
                else:
                    self.assertNotIn("compare_points", [item.key for item in app.toggle])
                    self.assertNotIn("channel", [item.key for item in app.selectbox])
                if kind != "Amazon":
                    app.text_input(key="merchant").set_value("Marriott" if kind == "Hotel" else "Store").run()
                app.button(key="find").click().run()
                self.assertFalse(app.exception)
                report = app.session_state["analysis"]
                self.assertEqual(report["inputs"]["purchase_type"], kind.lower())
                self.assertIsNone(report["award"])
                self.assertNotIn("Delta", report["inputs"]["merchant"])
                if kind != "Hotel":
                    self.assertEqual(report["inputs"]["booking_channel"], "")
                    self.assertNotIn("direct", report["answer"].lower())
                    self.assertIn("BEST CARD TO USE", " ".join(item.proto.body for item in app.get("html")))


if __name__ == "__main__":
    unittest.main()
