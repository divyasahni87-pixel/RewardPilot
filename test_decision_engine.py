from decision_engine import (
    calculate_cash_rewards,
    compare_cash_cards,
    evaluate_award_option
)
from unittest.mock import patch


cards = [
    "delta_platinum_amex",
    "amex_gold",
    "chase_sapphire_preferred"
]


balances = {
    "Delta SkyMiles": 50000,
    "Amex Membership Rewards": 70000,
    "Chase Ultimate Rewards": 85000
}


print()
print("=" * 60)
print("CASH PAYMENT OPTIONS")
print("=" * 60)


purchase = {
    "type": "flight",
    "merchant": "Delta",
    "booking_channel": "direct"
}

cash_results = compare_cash_cards(
    card_ids=cards,
    amount=1500,
    purchase=purchase
)


for result in cash_results:

    print()

    print(
        result["card_name"]
    )

    print(
        "Mapped category:",
        result["mapped_category"]
    )

    print(
        "Earn rate:",
        result["earn_rate"],
        result["unit"]
    )

    print(
        "Rewards earned:",
        result["reward_amount"],
        result["reward_program"]
    )

    reward_value = result["reward_value"]

    if reward_value is not None:
        print(
            "Valuation assumption:",
            reward_value["cents_per_point"],
            "cents per point"
        )
        print(
            "Estimated reward value:",
            f'${reward_value["estimated_value_usd"]:.2f}'
        )
    else:
        print("Valuation assumption: unavailable")
        print("Estimated reward value: unavailable")


print()
print("=" * 60)
print("POINTS OPTION")
print("=" * 60)


award_result = evaluate_award_option(
    target_program="Delta SkyMiles",
    required_points=90000,
    taxes_fees=33.60,
    cash_price=1500,
    balances=balances
)


print(
    "Required Delta miles:",
    award_result["required_points"]
)

print(
    "Existing Delta miles:",
    award_result["existing_points"]
)

print(
    "Shortfall:",
    award_result["shortfall"]
)

print(
    "Value:",
    award_result.get(
        "cents_per_point"
    ),
    "cents per point"
)


print()
print("TRANSFER OPTIONS")


for option in award_result[
    "transfer_options"
]:

    print()
    print(
        option["from_program"]
    )

    print(
        "Available:",
        option["available_points"]
    )

    print(
        "Required transfer:",
        option["required_transfer"]
    )

    print(
        "Can cover:",
        option["can_cover_shortfall"]
    )


def test_prime_visa_cashback():
    # Use the catalog category directly; Prime Visa mapping is separate logic.
    with patch("decision_engine.get_reward_value") as valuation_lookup:
        result = calculate_cash_rewards("prime_visa", 1000, "amazon")
        valuation_lookup.assert_not_called()

    assert result["unit"] == "percent_cashback"
    assert result["earn_rate"] == 5.0
    assert result["reward_amount"] == 50.0
    assert result["reward_value"]["estimated_value_usd"] == 50.0
    assert "cents_per_point" not in result["reward_value"]

    print()
    print("Prime Visa cash-back test: PASS")
    print("Amazon purchase: $1,000.00 at 5%")
    print(f'Cash back earned: ${result["reward_amount"]:.2f}')
    print(
        "Estimated reward value:",
        f'${result["reward_value"]["estimated_value_usd"]:.2f}'
    )


if __name__ == "__main__":
    test_prime_visa_cashback()
