"""Exercise the existing engine using a demo wallet retrieved from SQLite."""

import json

from decision_engine import compare_cash_cards, evaluate_award_option
from seed_demo_wallet import seed_demo_wallet
from wallet_db import get_reward_balances, get_user_cards, initialize_database


def test_wallet_decision():
    initialize_database()
    user_id = seed_demo_wallet()
    assert seed_demo_wallet() == user_id
    cards = get_user_cards(user_id)
    balances = get_reward_balances(user_id)

    print("RETRIEVED DEMO WALLET")
    print(json.dumps({"user_id": user_id, "name": "Demo User",
                      "cards": cards, "balances": balances}, indent=2))

    cash_results = compare_cash_cards(
        cards, 1500,
        {"type": "flight", "merchant": "Delta", "booking_channel": "direct"},
    )
    assert [
        (row["card_id"], row["mapped_category"], row["earn_rate"],
         row["reward_amount"], row["reward_value"]["estimated_value_usd"])
        for row in cash_results
    ] == [
        ("amex_gold", "flight_direct_or_amex_travel", 3.0, 4500.0, 67.50),
        ("delta_platinum_amex", "delta_purchase", 3.0, 4500.0, 54.00),
        ("chase_sapphire_preferred", "travel_other", 2.0, 3000.0, 45.00),
    ]
    print("\nCASH PAYMENT OPTIONS")
    for row in cash_results:
        print(f'\n{row["card_name"]}')
        print("Mapped category:", row["mapped_category"])
        print("Earn rate:", row["earn_rate"], row["unit"])
        print("Rewards earned:", row["reward_amount"], row["reward_program"])
        print("Valuation assumption:", row["reward_value"]["cents_per_point"],
              "cents per point")
        print(f'Estimated reward value: ${row["reward_value"]["estimated_value_usd"]:.2f}')

    award = evaluate_award_option("Delta SkyMiles", 90000, 33.60, 1500, balances)
    assert award["existing_points"] == 50000
    assert award["shortfall"] == 40000
    assert award["can_book_directly"] is False
    assert award["cents_per_point"] == 1.63
    assert len(award["transfer_options"]) == 1
    transfer = award["transfer_options"][0]
    assert transfer["from_program"] == "Amex Membership Rewards"
    assert transfer["available_points"] == 70000
    assert transfer["required_transfer"] == 40000
    assert transfer["can_cover_shortfall"] is True
    assert transfer["ratio"] == "1000:1000"
    print("\nPOINTS OPTION / TRANSFER OPTIONS")
    print(json.dumps(award, indent=2))
    print("\nPASS: SQLite wallet produces the expected cash and award decisions.")


if __name__ == "__main__":
    test_wallet_decision()
