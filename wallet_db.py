"""SQLite storage for user wallets; universal reward rules stay in JSON."""

from contextlib import contextmanager
from pathlib import Path
import sqlite3
import math
import json


DB_PATH = Path(__file__).resolve().parent / "data" / "rewardpilot.db"


@contextmanager
def _connection():
    connection = sqlite3.connect(DB_PATH)
    try:
        connection.execute("PRAGMA foreign_keys = ON")
        with connection:
            yield connection
    finally:
        connection.close()


def initialize_database():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _connection() as connection:
        connection.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS user_cards (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                card_id TEXT NOT NULL,
                nickname TEXT NULL,
                active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, card_id),
                FOREIGN KEY(user_id) REFERENCES users(id)
            );
            CREATE TABLE IF NOT EXISTS reward_balances (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                reward_program TEXT NOT NULL,
                balance REAL NOT NULL DEFAULT 0,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, reward_program),
                FOREIGN KEY(user_id) REFERENCES users(id)
            );
        """)


def create_user(name):
    """Create a user and return its ID. Names need not be unique."""
    with _connection() as connection:
        cursor = connection.execute("INSERT INTO users (name) VALUES (?)", (name,))
        return cursor.lastrowid


def get_or_create_user(name):
    """Reuse the first matching user for repeatable demo seeding."""
    with _connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute(
            "SELECT id FROM users WHERE name = ? ORDER BY id LIMIT 1", (name,)
        ).fetchone()
        if row is not None:
            return row[0]
        cursor = connection.execute("INSERT INTO users (name) VALUES (?)", (name,))
        return cursor.lastrowid


def add_user_card(user_id, card_id, nickname=None):
    """Add or reactivate a card, retaining its nickname when none is supplied."""
    catalog = json.loads((Path(__file__).resolve().parent / "data/card_catalog.json").read_text(encoding="utf-8"))
    if card_id not in {card["card_id"] for card in catalog}:
        raise ValueError("Choose a card from the card catalog.")
    with _connection() as connection:
        connection.execute("""
            INSERT INTO user_cards (user_id, card_id, nickname) VALUES (?, ?, ?)
            ON CONFLICT(user_id, card_id) DO UPDATE SET
                active = 1,
                nickname = COALESCE(excluded.nickname, user_cards.nickname)
        """, (user_id, card_id, nickname))


def get_user_cards(user_id):
    """Return active card IDs in insertion order for compare_cash_cards()."""
    with _connection() as connection:
        rows = connection.execute("""
            SELECT card_id FROM user_cards
            WHERE user_id = ? AND active = 1 ORDER BY id
        """, (user_id,)).fetchall()
        return [row[0] for row in rows]


def upsert_reward_balance(user_id, reward_program, balance):
    """Set the current balance, replacing any previous value for this program."""
    save_reward_balances(user_id, {reward_program: balance})


def save_reward_balances(user_id, balances):
    """Validate all edits before committing a single atomic balance update."""
    for balance in balances.values():
        if not isinstance(balance, (int, float)) or not math.isfinite(balance) or balance < 0:
            raise ValueError("Balances must be finite, nonnegative numbers.")
    with _connection() as connection:
        if connection.execute("SELECT id FROM users WHERE id = ?", (user_id,)).fetchone() is None:
            raise sqlite3.IntegrityError("Wallet user does not exist")
        connection.executemany("""
            INSERT INTO reward_balances (user_id, reward_program, balance)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id, reward_program) DO UPDATE SET
                balance = excluded.balance,
                updated_at = CURRENT_TIMESTAMP
        """, [(user_id, program, balance) for program, balance in balances.items()])


def get_reward_balances(user_id):
    with _connection() as connection:
        rows = connection.execute("""
            SELECT reward_program, balance FROM reward_balances
            WHERE user_id = ? ORDER BY id
        """, (user_id,)).fetchall()
        return dict(rows)


def get_user(user_id):
    with _connection() as connection:
        row = connection.execute("SELECT id, name FROM users WHERE id = ?", (user_id,)).fetchone()
        return {"id": row[0], "name": row[1]} if row else None


def initialize_user_wallet(user_id=1):
    """Explicit first-run setup; never replace an existing user or seed rewards."""
    with _connection() as connection:
        connection.execute("INSERT INTO users (id, name) VALUES (?, ?) ON CONFLICT(id) DO NOTHING",
                           (user_id, "My Wallet"))


def set_card_active(user_id, card_id, active):
    with _connection() as connection:
        cursor = connection.execute("UPDATE user_cards SET active = ? WHERE user_id = ? AND card_id = ?",
                                    (int(bool(active)), user_id, card_id))
        if cursor.rowcount == 0:
            raise ValueError("This card is not in your wallet.")
