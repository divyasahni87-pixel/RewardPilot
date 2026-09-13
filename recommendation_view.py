"""Format verified tool results for presentation; no reward calculations."""


def format_recommendation(report):
    top = report["cash"][0]
    purchase_type = report["inputs"].get("purchase_type", "flight")
    travel = purchase_type in ("flight", "hotel")
    unit = "points" if purchase_type == "hotel" else "miles"
    value = top.get("reward_value")
    cash = (f'{top["card_name"]} is the best cash option, earning '
            f'{top["reward_amount"]:,.0f} {top["reward_program"]}')
    if top.get("unit") == "percent_cashback":
        cash = f'{top["card_name"]} is the best cash option, earning ${top["reward_amount"]:,.2f} cash back'
    if value is not None:
        cash += (f' with an estimated reward value of ${value["estimated_value_usd"]:,.2f}'
                 ' under the current valuation assumptions.')
    else:
        cash += '. No estimated dollar valuation is available.'
    channel = report["inputs"]["booking_channel"]
    if channel and travel:
        from ui_agent import channel_label
        cash += f' Booking channel: {channel_label(report["inputs"])}.'
    elif travel:
        cash += ' Booking channel is unconfirmed; confirm it before choosing a card. No direct-booking bonus was assumed.'
    if not travel:
        cash = cash.replace("best cash option", "best card to use")
    sections = [("BEST CASH OPTION\n" if travel else "BEST CARD TO USE\n") + cash]
    award = report["award"] if report["inputs"]["compare_points"] else None
    if award:
        points = (f'The quoted award costs {award["required_points"]:,.0f} {award["target_program"]}'
                  f' + ${award["taxes_fees"]:,.2f}. Your balance is {award["existing_points"]:,.0f},'
                  f' leaving a {award["shortfall"]:,.0f} {unit} shortfall.'
                  f' Redemption value: {award["cents_per_point"]:.2f}¢ per point.')
        for option in award.get("transfer_options", []):
            if option["can_cover_shortfall"]:
                points += (f' A possible transfer of {option["required_transfer"]:,.0f}'
                           f' {option["from_program"]} can cover the shortfall (ratio {option["ratio"]}).')
        sections.append("BEST POINTS OPTION\n" + points)
        if report.get("policy_search_called") and report["evidence"]:
            conditions = []
            for source in report["evidence"]:
                body = source["text"].split("## How RewardPilot")[0].split("## Example retrieval questions")[0]
                facts = [line.strip().removeprefix("- ") for line in body.splitlines()
                         if line.startswith("- ") and any(word in line.lower() for word in
                             ("final", "availability", "operated", "fee", "$", "booking must"))]
                if facts:
                    conditions.append(" ".join(facts) + f' ({source["title"]}; last verified {source["last_verified"]}.)')
            if any(source.get("policy_type") == "award_discount" for source in report["evidence"]):
                conditions.append(f'Your discount-inclusion answer: {report["inputs"]["discount_status"]}. The entered award price was used unchanged.')
            if conditions:
                sections.append("IMPORTANT CONDITIONS\n" + "\n\n".join(conditions))
    recommendation = f'Choose {top["card_name"]} if paying cash.'
    overall = report.get("overall_comparison") if award else None
    if overall:
        labels = {"points": "BEST OVERALL: USE POINTS", "cash": "BEST OVERALL: PAY CASH",
                  "use_points": "BEST OVERALL: USE POINTS", "pay_cash": "BEST OVERALL: PAY CASH",
                  "close_call": "Close call", "unavailable": "Overall comparison unavailable"}
        summary = ("Close call" if overall.get("status") == "close_call" else
                   labels.get(overall["overall_winner"], "Overall comparison unavailable"))
        if overall.get("status") == "conditional_winner":
            summary = "CONDITIONAL BEST OPTION: " + ("USE POINTS" if overall["leading_option"] == "points" else "PAY CASH")
        elif overall.get("status") == "close_call" and overall.get("leading_option"):
            summary += " — " + ("Points currently have a slight edge" if overall["leading_option"] == "points" else "Cash currently has a slight edge")
        if overall["estimated_advantage_usd"] is not None:
            label = "Estimated advantage"
            summary += f'\n{label}: ${overall["estimated_advantage_usd"]:,.2f}.'
        sections.append(summary + "\n" + overall["reason"])
        sections.extend(overall.get("conditions", []))
    if award:
        recommendation += ' The quoted points option is a separate alternative; review its balance requirements and any retrieved conditions before proceeding.'
    sections.append("RECOMMENDATION\n" + recommendation)
    return "\n\n".join(sections)
