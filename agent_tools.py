"""Thin, read-only wrappers around RewardPilot's existing Python functions."""

from langchain.tools import tool

from decision_engine import CARDS, TRANSFER_RULES, compare_cash_cards, evaluate_award_option
from rag_retriever import retrieve_policy_context
from wallet_db import get_reward_balances, get_user_cards


@tool
def get_rewards_wallet(user_id: int) -> dict:
    """Retrieve the user's active owned card IDs and reward-program balances."""
    return {"card_ids": get_user_cards(user_id),
            "reward_balances": get_reward_balances(user_id)}


@tool
def compare_cash_payment(user_id: int, amount: float, purchase_type: str,
                         merchant: str, booking_channel: str = "", purchase_method: str = "",
                         prepaid: bool = False, prime_member: bool = False,
                         is_us_supermarket: bool = False, online_grocery_eligible: bool = False) -> list:
    """Rank owned cards by estimated cash-payment rewards using Python.

    Pass the supplied purchase_type and eligibility confirmations exactly.
    Never infer prepaid, Prime membership, or grocery eligibility. Optional
    purchase_method is in_store, online, or empty when unknown.
    Supply the actual booking channel, or label it explicitly as a hypothetical
    in your answer if unknown. The existing mapper recognizes direct and
    amex_travel for eligible Amex flight earning.
    """
    if amount < 0:
        raise ValueError("amount must be nonnegative")
    purchase = {"type": purchase_type, "merchant": merchant,
                "booking_channel": booking_channel}
    if purchase_type != "flight":
        purchase.update(purchase_method=purchase_method, prepaid=prepaid, prime_member=prime_member,
                        is_us_supermarket=is_us_supermarket, online_grocery_eligible=online_grocery_eligible)
    return compare_cash_cards(get_user_cards(user_id), amount, purchase)


@tool
def evaluate_points_redemption(user_id: int, target_program: str,
                               required_points: float, cash_price: float,
                               taxes_fees: float) -> dict:
    """Evaluate a quoted award's value, shortfall and available transfer paths.

    Uses SQLite balances and deterministic Python. Does not verify live award
    availability, apply eligibility discounts, or execute any transfer.
    target_program must be the exact program name, e.g. 'Delta SkyMiles',
    not an airline abbreviation such as 'Delta'.
    """
    if required_points <= 0 or cash_price < 0 or taxes_fees < 0:
        raise ValueError("Points must be positive; prices and fees nonnegative")
    balances = get_reward_balances(user_id)
    # Accept programs with no current balance if supported by structured rules.
    programs = set(balances) | {card["reward_program"] for card in CARDS}
    programs.update(rule["to_program"] for rule in TRANSFER_RULES)
    if target_program not in programs:
        return {"error": "Unknown program; retry with its exact name.",
                "supported_programs": sorted(programs)}
    return evaluate_award_option(target_program, required_points, taxes_fees,
                                 cash_price, balances)


@tool
def search_rewards_policy(question: str, program: str | None = None,
                          policy_type: str | None = None) -> list:
    """Retrieve policy evidence and source metadata for eligibility or restrictions.

    Returns evidence only, not another LLM's answer. An empty list means there
    is no sufficiently relevant evidence; do not invent a policy in that case.
    Use program and policy_type whenever the reward program or policy type is
    known. Exact examples:
    - Amex transfers: program='Amex Membership Rewards', policy_type='transfer_policy'.
    - Delta TakeOff 15: program='Delta SkyMiles', policy_type='award_discount'.
    - Amex Platinum hotel earning: program='Amex Membership Rewards', policy_type='earning_rule'.
    Other policy types: baggage, certificate, redemption_policy.
    A filtered search answers only that policy type. For a Delta award funded
    by an Amex transfer, make TWO separate searches: Amex transfer_policy and
    Delta award_discount. A discount result cannot establish transfer conditions.
    """
    return retrieve_policy_context(question, program=program, policy_type=policy_type)


REWARDPILOT_TOOLS = [get_rewards_wallet, compare_cash_payment,
                    evaluate_points_redemption, search_rewards_policy]
