"""Wallet editing tests use isolated SQLite files, never the real wallet."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest
import wallet_db as db
import ui_agent
from test_app import offline_run
from decision_engine import compare_cash_cards


class WalletManagementTests(unittest.TestCase):
    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        patcher = patch.object(db, "DB_PATH", Path(directory.name) / "wallet.db")
        patcher.start()
        self.addCleanup(patcher.stop)
        db.initialize_database()
        db.initialize_user_wallet()

    def app(self):
        return AppTest.from_file("app.py", default_timeout=40).run()

    def test_deactivation_reactivation_and_validation(self):
        db.add_user_card(1, "amex_gold")
        db.add_user_card(1, "amex_gold")
        with db._connection() as conn:
            original = conn.execute("SELECT id FROM user_cards").fetchone()[0]
            self.assertEqual(conn.execute("SELECT count(*) FROM user_cards").fetchone()[0], 1)
        db.upsert_reward_balance(1, "Amex Membership Rewards", 70000)
        db.set_card_active(1, "amex_gold", False)
        self.assertEqual(db.get_user_cards(1), [])
        self.assertEqual(compare_cash_cards(db.get_user_cards(1), 450, {"type": "flight"}), [])
        self.assertEqual(db.get_reward_balances(1)["Amex Membership Rewards"], 70000)
        db.add_user_card(1, "amex_gold")
        with db._connection() as conn:
            self.assertEqual(conn.execute("SELECT id, active FROM user_cards").fetchone(), (original, 1))
            conn.execute("UPDATE reward_balances SET updated_at = '2000-01-01'")
        db.upsert_reward_balance(1, "Amex Membership Rewards", 0)
        with db._connection() as conn:
            self.assertNotEqual(conn.execute("SELECT updated_at FROM reward_balances").fetchone()[0], "2000-01-01")
        for invalid in (-1, float("nan"), float("inf")):
            with self.assertRaises(ValueError):
                db.upsert_reward_balance(1, "Amex Membership Rewards", invalid)
        with self.assertRaises(ValueError):
            db.add_user_card(1, "not_a_catalog_card")

    def test_editor_add_duplicate_remove_and_immediate_recommendation(self):
        db.add_user_card(1, "delta_platinum_amex")
        app = self.app()
        app.button(key="manage_wallet").click().run()
        self.assertTrue({"Add a card", "Your cards", "Reward balances"}.issubset(
            {item.value for item in app.subheader}))
        self.assertEqual(app.button(key="wallet_add").proto.type, "secondary")
        app.selectbox(key="wallet_card").select("amex_gold").run()
        app.button(key="wallet_add").click().run()
        self.assertFalse(app.exception)
        self.assertIn("amex_gold", db.get_user_cards(1))
        self.assertIn("Card added", [item.value for item in app.success])
        self.assertTrue(app.session_state["wallet_editor_open"])
        app.button(key="wallet_add").click().run()
        self.assertIn("This card is already in your wallet.", [item.value for item in app.info])
        app.button(key="wallet_remove_delta_platinum_amex").click().run()
        self.assertEqual(db.get_user_cards(1), ["amex_gold"])
        self.assertIn("Card removed", [item.value for item in app.success])
        app.button(key="wallet_done").click().run()
        with patch.object(ui_agent, "run_analysis", side_effect=offline_run):
            app.button(key="find").click().run()
        self.assertFalse(app.exception)
        self.assertEqual(app.session_state["analysis"]["cash"][0]["card_id"], "amex_gold")

    def test_shared_program_balances_and_orphan_preservation(self):
        for card in ("amex_gold", "amex_platinum"):
            db.add_user_card(1, card)
        db.upsert_reward_balance(1, "Delta SkyMiles", 50000)
        app = self.app()
        app.button(key="manage_wallet").click().run()
        self.assertEqual(sum(item.label == "Amex Membership Rewards" for item in app.number_input), 1)
        self.assertEqual(next(button for button in app.button if button.label == "Save balances").proto.type, "primary")
        app.number_input(key="wallet_balance_Amex Membership Rewards").set_value(12345).run()
        next(button for button in app.button if button.label == "Save balances").click().run()
        self.assertFalse(app.exception)
        self.assertEqual(db.get_reward_balances(1), {"Delta SkyMiles": 50000, "Amex Membership Rewards": 12345})
        self.assertIsNone(app.session_state["analysis"])
        self.assertIn("Wallet updated.", [item.value for item in app.success])
        with patch.object(ui_agent, "run_analysis", side_effect=offline_run):
            app.button(key="example").click().run()
            app.button(key="find").click().run()
        self.assertFalse(app.exception)
        option = app.session_state["analysis"]["award"]["transfer_options"][0]
        self.assertEqual(option["available_points"], 12345)
        self.assertFalse(option["can_cover_shortfall"])

    def test_empty_and_missing_user(self):
        app = self.app()
        self.assertTrue(any("Your wallet is empty" in item.value for item in app.info))
        with db._connection() as conn:
            conn.execute("DELETE FROM users")
        app = self.app()
        self.assertFalse(app.exception)
        app.button(key="create_wallet").click().run()
        self.assertIsNotNone(db.get_user(1))
        self.assertEqual(db.get_user_cards(1), [])

    def test_new_program_shared_program_and_reopen(self):
        db.add_user_card(1, "delta_platinum_amex")
        db.upsert_reward_balance(1, "Delta SkyMiles", 50000)
        app = self.app()
        app.button(key="manage_wallet").click().run()
        app.selectbox(key="wallet_card").select("delta_reserve_amex").run()
        app.button(key="wallet_add").click().run()
        self.assertFalse(app.exception)
        self.assertEqual(len(db.get_user_cards(1)), 2)
        self.assertTrue(app.session_state["wallet_editor_open"])
        self.assertEqual(sum(item.label == "Delta SkyMiles" for item in app.number_input), 1)
        self.assertEqual(app.number_input(key="wallet_balance_Delta SkyMiles").value, 50000)
        app.selectbox(key="wallet_issuer").select("Chase").run()
        app.selectbox(key="wallet_card").select("marriott_boundless").run()
        app.button(key="wallet_add").click().run()
        self.assertFalse(app.exception)
        self.assertTrue(app.session_state["wallet_editor_open"])
        self.assertIn("marriott_boundless", db.get_user_cards(1))
        self.assertEqual(app.number_input(key="wallet_balance_Marriott Bonvoy").value, 0)
        app.number_input(key="wallet_balance_Marriott Bonvoy").set_value(25000).run()
        next(button for button in app.button if button.label == "Save balances").click().run()
        self.assertFalse(app.exception)
        self.assertFalse(app.session_state["wallet_editor_open"])
        self.assertEqual(db.get_reward_balances(1)["Marriott Bonvoy"], 25000)
        self.assertTrue(any("25,000" in item.proto.body and "Marriott Bonvoy" in item.proto.body for item in app.get("html")))
        app.button(key="manage_wallet").click().run()
        self.assertEqual(app.number_input(key="wallet_balance_Marriott Bonvoy").value, 25000)
        app.button(key="wallet_remove_marriott_boundless").click().run()
        self.assertTrue(app.session_state["wallet_editor_open"])
        self.assertIn("**Other reward balances**", [item.value for item in app.markdown])
        self.assertEqual(app.number_input(key="wallet_balance_Marriott Bonvoy").value, 25000)
        app.button(key="wallet_add").click().run()
        self.assertFalse(app.exception)
        self.assertEqual(app.number_input(key="wallet_balance_Marriott Bonvoy").value, 25000)
        self.assertEqual(sum(item.label == "Marriott Bonvoy" for item in app.number_input), 1)


if __name__ == "__main__":
    unittest.main()
