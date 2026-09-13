"""Run again to restore the demo cards and balances without duplicate rows."""

from wallet_db import (
    add_user_card,
    get_or_create_user,
    initialize_database,
    upsert_reward_balance,
)


def seed_demo_wallet():
    initialize_database()
    user_id = get_or_create_user("Demo User")
    for card_id in (
        "delta_platinum_amex",
        "amex_gold",
        "chase_sapphire_preferred",
    ):
        add_user_card(user_id, card_id)

    for program, balance in {
        "Delta SkyMiles": 50000,
        "Amex Membership Rewards": 70000,
        "Chase Ultimate Rewards": 85000,
    }.items():
        upsert_reward_balance(user_id, program, balance)
    return user_id


if __name__ == "__main__":
    print(f"Seeded Demo User (id={seed_demo_wallet()})")
