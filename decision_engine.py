from purchase_mapper import map_purchase_to_card_category
import json
from pathlib import Path


DATA_DIR = Path("data")


def load_json(filename):
    path = DATA_DIR / filename

    with open(path, "r", encoding="utf-8") as file:
        return json.load(file)


CARDS = load_json("card_catalog.json")
TRANSFER_RULES = load_json("transfer_rules.json")
REDEMPTION_RULES = load_json("redemption_rules.json")
REWARD_VALUATIONS = load_json("reward_valuations.json")
COMPARISON_SETTINGS = load_json("comparison_settings.json")


def get_reward_value(reward_program, reward_amount):
    """Estimate USD value using configured CPP, preserving valuation metadata."""
    valuation = REWARD_VALUATIONS.get(reward_program)

    if not valuation or valuation.get("cents_per_point") is None:
        return None

    return {
        **valuation,
        "estimated_value_usd": (
            reward_amount * valuation["cents_per_point"] / 100
        )
    }


def get_card(card_id):
    for card in CARDS:
        if card["card_id"] == card_id:
            return card

    return None


def compare_payment_options(cash_results, award, *, booking_channel_known=True,
                            close_call_fraction=None):
    """Compare quoted costs using consumed currencies; never infer transfer fees."""
    if award is None:
        return None
    threshold = (COMPARISON_SETTINGS["close_call_fraction"]
                 if close_call_fraction is None else close_call_fraction)
    if not 0 <= threshold <= 1:
        raise ValueError("close_call_fraction must be between 0 and 1")
    result = {
        "status": "insufficient_data", "overall_winner": None,
        "leading_option": None, "conditions": [], "transfer_fee_usd": 0.0,
        "transfer_fee_source": None,
        "cash_effective_cost": None, "points_effective_cost": None,
        "estimated_advantage_usd": None, "cash_reward_value": None,
        "points_opportunity_cost": None, "valuation_assumptions": {},
        "reason": "", "close_call_fraction": threshold,
        "reason_code": None, "missing_fields": [],
        "transfer_options": award.get("transfer_options", []), "selected_transfer": None,
    }
    required = ("target_program", "required_points", "cash_price", "taxes_fees", "shortfall")
    result["missing_fields"] = [field for field in required if award.get(field) is None]
    if result["missing_fields"]:
        result["reason_code"] = "missing_award_data"
        result["reason"] = "Overall comparison is unavailable: required award data is missing."
        return result
    if cash_results and cash_results[0].get("reward_value") is not None:
        result["cash_reward_value"] = cash_results[0]["reward_value"]["estimated_value_usd"]
        result["cash_effective_cost"] = round(award["cash_price"] - result["cash_reward_value"], 2)
    shortfall = award.get("shortfall", 0)
    consumed = [(award["target_program"], award["required_points"])]
    limitations = []
    if shortfall > 0:
        paths = [path for path in award.get("transfer_options", []) if path["can_cover_shortfall"]]
        if len(paths) != 1:
            result["reason_code"] = "no_feasible_transfer" if not paths else "multiple_transfer_paths"
            result["reason"] = ("Overall comparison is unavailable: no single feasible transfer path "
                                "has been determined.")
            return result
        path = paths[0]
        result["selected_transfer"] = dict(path)
        rule = get_transfer_rule(path["from_program"], award["target_program"])
        if not rule or rule.get("ratio_from", 0) <= 0 or rule.get("ratio_to", 0) <= 0:
            result["reason_code"] = "missing_transfer_ratio"
            result["missing_fields"] = ["transfer_ratio"]
            result["reason"] = "Overall comparison is unavailable: a valid transfer ratio is missing."
            return result
        consumed = [(award["target_program"], award["required_points"] - shortfall),
                    (path["from_program"], path["required_transfer"])]
        fee_rule = next((fee for fee in COMPARISON_SETTINGS["transfer_fees"]
                        if fee["from_program"] == path["from_program"]
                        and fee["to_program"] == award["target_program"]), None)
        if fee_rule:
            result["transfer_fee_usd"] = round(min(
                path["required_transfer"] * fee_rule["usd_per_source_point"], fee_rule["maximum_usd"]), 2)
            result["transfer_fee_source"] = dict(fee_rule)
        else:
            result["transfer_fee_usd"] = None
            limitations.append("Transfer fees are unconfirmed; displayed points cost excludes any unquantified fee.")
        limitations.append("Confirm award availability and transfer-policy requirements before transferring points.")
    opportunity_cost = 0
    for program, amount in consumed:
        if amount == 0:
            continue
        valuation = get_reward_value(program, amount)
        if valuation is None:
            result["reason_code"] = "missing_reward_valuation"
            result["missing_fields"] = [f"valuation:{program}"]
            result["reason"] = f"Overall comparison is unavailable: a configured valuation is missing for {program}."
            return result
        result["valuation_assumptions"][program] = {**valuation, "points_consumed": amount}
        opportunity_cost += valuation["estimated_value_usd"]
    result["points_opportunity_cost"] = round(opportunity_cost, 2)
    result["points_effective_cost"] = round(award["taxes_fees"] + opportunity_cost
                                            + (result["transfer_fee_usd"] or 0), 2)
    if not cash_results or any(row.get("reward_value") is None for row in cash_results):
        result["reason_code"] = "missing_reward_valuation" if cash_results else "missing_cash_data"
        result["missing_fields"] = ([f'valuation:{row["reward_program"]}' for row in cash_results
                                     if row.get("reward_value") is None] if cash_results else ["cash_results"])
        result["reason"] = "Overall comparison is unavailable: a configured cash-reward valuation is missing."
        return result
    if not booking_channel_known:
        limitations.append("Confirm the booking channel to verify cash rewards.")
    result["conditions"] = limitations
    difference = round(result["cash_effective_cost"] - result["points_effective_cost"], 2)
    result["estimated_advantage_usd"] = abs(difference)
    result["leading_option"] = "points" if difference > 0 else "cash" if difference < 0 else None
    higher_cost = max(abs(result["cash_effective_cost"]), abs(result["points_effective_cost"]))
    if difference == 0 or abs(difference) < threshold * higher_cost:
        result["status"] = "close_call"
        result["reason_code"] = "close_call_" + (result["leading_option"] or "tie")
        result["reason"] = ("The difference is small. Confirm award availability before transferring points."
                            if shortfall > 0 else "The difference is small under the current valuation assumptions.")
        if (result["selected_transfer"] and result["selected_transfer"]["from_program"] == "Amex Membership Rewards"
                and award["target_program"] == "Delta SkyMiles"):
            result["reason"] = ("The difference is small. Confirm award availability before transferring "
                                "points because transfers are final.")
    elif limitations:
        result["status"] = "conditional_winner"
        result["reason_code"] = "conditional_" + result["leading_option"] + "_advantage"
        result["reason"] = "The leading option has a meaningful estimated advantage, subject to the listed conditions."
    else:
        result["status"] = "winner"
        result["reason_code"] = "clear_" + result["leading_option"] + "_advantage"
        result["overall_winner"] = result["leading_option"]
        result["reason"] = ("The quoted points option has the lower estimated effective cost."
                            if difference > 0 else "Paying cash has the lower estimated effective cost.")
    result["reason"] += " Uses the quoted award unchanged and current point-value assumptions."
    return result


def get_earn_rate(card_id, category):
    card = get_card(card_id)

    if not card:
        return None

    # First look for exact category
    for rule in card.get("earn_rules", []):
        if rule["category"] == category:
            return rule

    # Fall back to "other"
    for rule in card.get("earn_rules", []):
        if rule["category"] == "other":
            return rule

    return None


def calculate_cash_rewards(
    card_id,
    amount,
    category
):
    card = get_card(card_id)

    if not card:
        return None

    rule = get_earn_rate(
        card_id,
        category
    )

    if not rule:
        return None

    rate = rule["rate"]
    unit = rule["unit"]

    if unit == "percent_cashback":
        reward_amount = amount * rate / 100
        reward_value = {
            "estimated_value_usd": reward_amount,
            "type": "cashback"
        }
    else:
        reward_amount = amount * rate
        reward_value = get_reward_value(
            card["reward_program"], reward_amount
        )

    return {
        "card_id": card_id,
        "card_name": card["card_name"],
        "reward_program": card["reward_program"],
        "purchase_amount": amount,
        "category": category,
        "earn_rate": rate,
        "unit": unit,
        "reward_amount": reward_amount,
        "reward_value": reward_value
    }


def compare_cash_cards(
    card_ids,
    amount,
    purchase
):
    results = []

    for card_id in card_ids:

        category = map_purchase_to_card_category(
            card_id,
            purchase
        )

        result = calculate_cash_rewards(
            card_id,
            amount,
            category
        )

        if result:
            result["mapped_category"] = category
            results.append(result)

    results.sort(
        # Unknown valuations sort last, without comparing raw reward amounts.
        key=lambda x: (
            x["reward_value"]["estimated_value_usd"]
            if x["reward_value"] is not None
            else float("-inf")
        ),
        reverse=True
    )

    return results


def get_transfer_rule(
    from_program,
    to_program
):
    for rule in TRANSFER_RULES:

        if (
            rule["from_program"] == from_program
            and
            rule["to_program"] == to_program
        ):
            return rule

    return None


def calculate_points_shortfall(
    required_points,
    existing_points
):
    return max(
        required_points - existing_points,
        0
    )


def calculate_transfer_needed(
    shortfall,
    ratio_from,
    ratio_to
):
    if ratio_to == 0:
        return None

    required_source_points = (
        shortfall
        * ratio_from
        / ratio_to
    )

    return required_source_points


def evaluate_award_option(
    target_program,
    required_points,
    taxes_fees,
    cash_price,
    balances
):
    existing_points = balances.get(
        target_program,
        0
    )

    shortfall = calculate_points_shortfall(
        required_points,
        existing_points
    )

    result = {
        "target_program": target_program,
        "required_points": required_points,
        "existing_points": existing_points,
        "shortfall": shortfall,
        "taxes_fees": taxes_fees,
        "cash_price": cash_price,
        "can_book_directly": shortfall == 0,
        "transfer_options": []
    }

    # Calculate cents-per-point
    if required_points > 0:

        cpp = (
            (cash_price - taxes_fees)
            / required_points
            * 100
        )

        result["cents_per_point"] = round(
            cpp,
            2
        )

    # If shortfall exists, look for transfer paths
    if shortfall > 0:

        for rule in TRANSFER_RULES:

            if rule["to_program"] != target_program:
                continue

            source_program = rule[
                "from_program"
            ]

            source_balance = balances.get(
                source_program,
                0
            )

            required_transfer = (
                calculate_transfer_needed(
                    shortfall,
                    rule["ratio_from"],
                    rule["ratio_to"]
                )
            )

            can_cover = (
                source_balance
                >= required_transfer
            )

            result[
                "transfer_options"
            ].append(
                {
                    "from_program":
                        source_program,

                    "available_points":
                        source_balance,

                    "required_transfer":
                        required_transfer,

                    "can_cover_shortfall":
                        can_cover,

                    "ratio":
                        f'{rule["ratio_from"]}:'
                        f'{rule["ratio_to"]}',

                    "notes":
                        rule.get(
                            "notes",
                            ""
                        )
                }
            )

    return result
