import json
from pathlib import Path

_CATEGORIES = {card["card_id"]: {rule["category"] for rule in card["earn_rules"]}
               for card in json.loads((Path(__file__).parent / "data/card_catalog.json").read_text(encoding="utf-8"))}


def map_purchase_to_card_category(card_id, purchase):

    purchase_type = (purchase.get("type") or "").strip().lower()
    merchant = (purchase.get("merchant") or "").strip().lower()
    booking_channel = (purchase.get("booking_channel") or "").strip().lower()
    categories = _CATEGORIES.get(card_id, set())
    candidates = []
    if purchase_type == "hotel":
        if booking_channel == "direct":
            if merchant in ("marriott", "marriott bonvoy"):
                candidates.append("marriott")
            candidates.append("hotel_direct")
        if booking_channel == "amex_travel" and purchase.get("prepaid") is True:
            candidates.append("amex_travel_prepaid_hotel")
        if booking_channel == "chase_travel" and (card_id != "prime_visa" or purchase.get("prime_member") is True):
            candidates.append("chase_travel")
        candidates.append("travel_other")
    elif purchase_type == "restaurant":
        candidates = ["restaurant", "dining", "grocery_gas_dining_combined"]
    elif purchase_type == "amazon":
        if purchase.get("prime_member") is True:
            candidates = ["amazon"]
    elif purchase_type == "groceries":
        method = purchase.get("purchase_method", "")
        excluded = any(name in merchant for name in ("walmart", "target", "costco", "sam's club", "sams club", "bj's"))
        if merchant in ("whole foods", "whole foods market") and purchase.get("prime_member") is True:
            candidates.append("whole_foods")
        if not excluded and merchant and method in ("in_store", "online"):
            if method == "online" and purchase.get("online_grocery_eligible") is True:
                candidates.append("online_grocery")
            if purchase.get("is_us_supermarket") is True:
                candidates.extend(["us_supermarket", "grocery_gas_dining_combined"])
    if purchase_type != "flight":
        return next((category for category in candidates if category in categories), "other")

    # Delta cards
    if card_id == "delta_platinum_amex":
        if (
            purchase_type == "flight"
            and merchant == "delta"
            and booking_channel == "direct"
        ):
            return "delta_purchase"

    # Amex Gold
    if card_id == "amex_gold":
        if (
            purchase_type == "flight"
            and booking_channel in [
                "direct",
                "amex_travel"
            ]
        ):
            return "flight_direct_or_amex_travel"

    # Chase Sapphire Preferred
    if card_id == "chase_sapphire_preferred":
        if purchase_type == "flight":
            if booking_channel == "chase_travel":
                return "chase_travel"
            return "travel_other"

    return "other"
