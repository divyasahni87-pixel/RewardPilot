"""Persistence checks use a temporary database, never the demo wallet."""

from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import wallet_db as db
from seed_demo_wallet import seed_demo_wallet


class WalletDatabaseTests(unittest.TestCase):
    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        patcher = patch.object(db, "DB_PATH", Path(directory.name) / "wallet.db")
        patcher.start()
        self.addCleanup(patcher.stop)
        db.initialize_database()

    def test_seed_is_repeatable(self):
        user_id = seed_demo_wallet()
        self.assertEqual(seed_demo_wallet(), user_id)
        with db._connection() as connection:
            counts = [connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                      for table in ("users", "user_cards", "reward_balances")]
        self.assertEqual(counts, [1, 3, 3])

    def test_users_are_isolated_and_balances_are_replaced(self):
        first = db.create_user("First user's wallet")
        second = db.create_user("Second user")
        db.add_user_card(first, "amex_gold", "Daily card")
        db.add_user_card(first, "amex_gold")
        db.upsert_reward_balance(first, "Amex Membership Rewards", 100)
        db.upsert_reward_balance(first, "Amex Membership Rewards", 250.5)
        self.assertEqual(db.get_user_cards(first), ["amex_gold"])
        self.assertEqual(db.get_reward_balances(first), {"Amex Membership Rewards": 250.5})
        self.assertEqual(db.get_user_cards(second), [])
        self.assertEqual(db.get_reward_balances(second), {})
        with db._connection() as connection:
            row = connection.execute("SELECT nickname, updated_at FROM user_cards "
                                     "JOIN reward_balances USING (user_id)").fetchone()
        self.assertEqual(row[0], "Daily card")
        self.assertIsNotNone(row[1])

    def test_inactive_cards_are_excluded_and_can_be_reactivated(self):
        user_id = db.create_user("Test")
        db.add_user_card(user_id, "amex_gold")
        with db._connection() as connection:
            connection.execute("UPDATE user_cards SET active = 0 WHERE user_id = ?", (user_id,))
        self.assertEqual(db.get_user_cards(user_id), [])
        db.add_user_card(user_id, "amex_gold")
        self.assertEqual(db.get_user_cards(user_id), ["amex_gold"])

    def test_foreign_keys_are_enforced(self):
        with self.assertRaises(sqlite3.IntegrityError):
            db.add_user_card(999, "amex_gold")
        with self.assertRaises(sqlite3.IntegrityError):
            db.upsert_reward_balance(999, "Delta SkyMiles", 100)


if __name__ == "__main__":
    unittest.main(verbosity=2)
