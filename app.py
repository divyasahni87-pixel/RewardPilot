"""RewardPilot's presentation layer. Reward calculations remain in the backend."""

from html import escape
from pathlib import Path
import logging

import altair as alt
import pandas as pd
import streamlit as st

import ui_agent
from decision_engine import get_card, REWARD_VALUATIONS
from wallet_db import get_user_cards, get_reward_balances
import wallet_db
from wallet_ui import manage_wallet

st.set_page_config(page_title="RewardPilot | Smarter rewards", page_icon="✈", layout="wide")
st.html(f"<style>{(Path(__file__).parent / 'assets/rewardpilot.css').read_text()}</style>")
st.session_state.setdefault("analysis", None)
st.session_state.setdefault("analysis_error", None)


def section(title, subtitle="", anchor=""):
    st.html(f'<div class="rp-section" id="{escape(anchor)}"><h2>{escape(title)}</h2><span>{escape(subtitle)}</span></div>')


def render_hero(cards, balances):
    st.html('''<header class="rp-nav"><div class="rp-brand">
        <svg class="rp-mark" viewBox="0 0 44 44" aria-hidden="true"><rect x="1" y="1" width="42" height="42" rx="13" fill="#142C44"/>
        <path d="M12 30L22 12L32 20L22 23Z" fill="none" stroke="#F3F6FA" stroke-width="2" stroke-linejoin="round"/>
        <path d="M12 30L22 23" stroke="#D7B56D" stroke-width="2"/><circle cx="32" cy="20" r="3" fill="#D7B56D"/></svg>
        <div>RewardPilot<span class="rp-descriptor">Rewards, optimized.</span></div></div>
        <span class="rp-ready"><span aria-hidden="true">●</span> Optimizer ready</span></header>
        <div class="rp-hero"><div><div class="rp-eyebrow">Your next journey, better rewarded</div>
        <h1>Turn every card, point, and mile<br>into a smarter decision.</h1>
        <p>Know when to pay cash, when to use points, and which card gives you the most value.</p></div>
        <div class="rp-art" aria-hidden="true"><div class="rp-orbit"></div><div class="rp-plane">✈</div>
        <div class="rp-artcard back">REWARDS, REIMAGINED<div class="rp-chip"></div>YOUR NEXT DESTINATION</div>
        <div class="rp-artcard front">REWARDPILOT<div class="rp-chip"></div>EVERY JOURNEY COUNTS</div></div></div>''')
    total = sum(balances.values())
    total_label = f"{total / 1000:,.0f}K" if total >= 1000 else f"{total:,.0f}"
    st.html(f'''<div class="rp-summary"><div><b>{len(cards)}</b><span>Cards in your wallet</span></div>
        <div><b>{total_label}</b><span>Points &amp; miles tracked</span></div>
        <div><b>{len(balances)}</b><span>Reward programs</span></div>
        <div><b style="font-size:16px">Optimizer ready</b><span>Wallet connected</span></div></div>''')


def render_wallet(cards, balances):
    section("My Rewards Wallet", "Your cards. Your possibilities.", "wallet")
    if st.button("Manage Wallet" if cards else "Add cards", key="manage_wallet", icon=":material/account_balance_wallet:"):
        st.session_state.wallet_editor_open = True
    if st.session_state.get("wallet_editor_open"):
        manage_wallet(1)
    if st.session_state.get("wallet_notice"):
        st.success(st.session_state.pop("wallet_notice"))
    if not cards:
        st.info("Your wallet is empty. Add your cards and reward balances to start optimizing.")
    columns_per_row = 2 if len(cards) == 4 else min(3, max(1, len(cards)))
    for start in range(0, len(cards), columns_per_row):
        for index, (column, card) in enumerate(zip(st.columns(columns_per_row), cards[start:start + columns_per_row])):
            with column:
                tone = ["silver", "gold", "navy"][index]
                program = card["reward_program"]
                balance = balances.get(program)
                balance_label = f"{balance:,.0f}" if balance is not None else "Not tracked"
                st.html(f'''<div class="rp-wallet-group"><div class="rp-wallet {tone}"><small>{escape(card.get("issuer", "Rewards card"))}</small>
                    <h3>{escape(card["card_name"])}</h3><p>{escape(program)}</p></div>
                    <div class="rp-balance"><span>Program balance</span><b>{balance_label}</b></div></div>''')
    # Programs can be shared by multiple cards; never imply separate balances.
    if len({card["reward_program"] for card in cards}) < len(cards):
        st.caption("Cards in the same rewards program share one program balance.")
    for program, balance in balances.items():
        if program not in {card["reward_program"] for card in cards}:
            st.caption(f"{program}: {balance:,.0f} tracked separately")


def reset_purchase_fields():
    for key in ("channel", "compare_points", "target_program", "required_points", "taxes_fees", "discount_status", *ui_agent.PURCHASE_DETAILS):
        st.session_state.pop(key, None)
    st.session_state.merchant = {"Flight": "Delta", "Amazon": "Amazon"}.get(st.session_state.purchase_type, "")
    st.session_state.analysis = None
    st.session_state.analysis_error = None


def load_example():
    reset_purchase_fields()
    st.session_state.update(purchase_type="Flight", merchant="Delta", amount=1500.0,
                            channel="Direct with airline", compare_points=True,
                            target_program="Delta SkyMiles", required_points=90000,
                            taxes_fees=33.60, discount_status="I'm not sure")


def render_purchase_form():
    section("What are you planning?", "Make your next booking work harder.", "optimizer")
    st.session_state.setdefault("merchant", "Delta")
    st.session_state.setdefault("amount", 1500.0)
    with st.container(border=True, key="planning"):
        st.button("Try an example", on_click=load_example, key="example", type="secondary")
        first = st.columns([1, 1.5, 1])
        kind = first[0].selectbox("Purchase type", ["Flight", "Hotel", "Groceries", "Restaurant", "Amazon"],
                                  key="purchase_type", on_change=reset_purchase_fields)
        travel = kind in ("Flight", "Hotel")
        merchant = first[1].text_input({"Flight": "Merchant / Airline", "Hotel": "Hotel / Merchant",
                                      "Groceries": "Store / Merchant", "Restaurant": "Restaurant / Merchant",
                                      "Amazon": "Merchant"}[kind], value=None, key="merchant", disabled=kind == "Amazon")
        amount = first[2].number_input("Purchase amount ($)", min_value=1.0, value=None, step=50.0, key="amount")
        channel, points, details = "", False, {}
        if travel:
            channels = ui_agent.HOTEL_CHANNELS if kind == "Hotel" else ui_agent.CHANNELS
            selected_channel = st.selectbox("Booking channel", list(channels), key="channel",
                                           help="Booking channel matters because reward multipliers can differ.")
            channel = channels[selected_channel]
            st.caption("Booking channel matters because reward multipliers can differ.")
            if kind == "Hotel" and channel == "amex_travel":
                details["prepaid"] = st.checkbox("This is a prepaid Amex Travel hotel booking", key="prepaid")
            if kind == "Hotel" and channel == "chase_travel":
                details["prime_member"] = st.checkbox("I have eligible Prime membership", key="prime_member")
            points = st.toggle("Compare a points option", value=False, key="compare_points")
        elif kind == "Groceries":
            methods = {"In store": "in_store", "Online": "online", "Other / Not sure": ""}
            method = st.selectbox("Purchase method", list(methods), index=2, key="purchase_method")
            details["purchase_method"] = methods[method]
            details["is_us_supermarket"] = st.checkbox("This is an eligible U.S. supermarket purchase", key="is_us_supermarket")
            if method == "Online":
                details["online_grocery_eligible"] = st.checkbox("This is eligible online grocery spending", key="online_grocery_eligible",
                    help="Excludes Target, Walmart and wholesale clubs. Leave unchecked if unsure.")
            details["prime_member"] = st.checkbox("I have eligible Prime membership", key="prime_member")
        elif kind == "Amazon":
            details["prime_member"] = st.checkbox("I have eligible Prime membership", key="prime_member")
        if kind in ("Groceries", "Restaurant"):
            st.caption("Spending caps may apply. Current earning assumes any applicable cap has not been reached.")
        program, required, taxes, discount = None, None, None, None
        if points:
            with st.container(border=True, key="award_inputs"):
                st.markdown("**Compare with a points option**")
                st.caption("Enter an award quote to compare it with paying cash.")
                cols = st.columns(3)
                program = cols[0].selectbox("Reward program", ["Delta SkyMiles"] if kind == "Flight" else ["Marriott Bonvoy", "Hilton Honors"], index=None,
                                            placeholder="Select a rewards program", key="target_program")
                required = cols[1].number_input("Points / miles required", min_value=1, value=None,
                                                placeholder="e.g. 90,000", step=1000, key="required_points")
                taxes = cols[2].number_input("Cash taxes & fees on the award", min_value=0.0, value=None,
                                             placeholder="e.g. 33.60", step=1.0, key="taxes_fees")
                st.caption("Use the points price and taxes shown by the airline or hotel for the same booking.")
                st.caption(":material/info: RewardPilot does not search live award availability yet. It evaluates the award price you provide.")
                if program and required:
                    discount = st.selectbox("Does this award price already include cardholder discounts?",
                                        ["I'm not sure", "Yes", "No"], key="discount_status",
                                        format_func=lambda value: {"I'm not sure": "I'm not sure",
                                            "Yes": "Yes, discounts are already included",
                                            "No": "No, discounts are not included"}[value])
                    st.caption("RewardPilot will not apply a discount automatically.")
        inputs = {"merchant": (merchant or "").strip(), "amount": amount, "booking_channel": channel, "purchase_type": kind.lower(), **details,
                  "compare_points": points, "target_program": program, "required_points": required,
                  "taxes_fees": taxes, "discount_status": discount}
        submitted = st.button("Find My Best Option", type="primary", icon=":material/flight_takeoff:",
                              width="stretch", key="find")
    return inputs, submitted


def render_cash_results(rows, overall_winner=False, everyday=False):
    top = rows[0]
    value = top.get("reward_value")
    with st.container(border=True, key="cash_result"):
        st.html('<span class="rp-pill rp-winner">' + ("BEST CARD TO USE" if everyday else "BEST CASH CARD") + "</span>")
        if overall_winner:
            st.html('<span class="rp-pill">BEST OVERALL</span>')
        st.subheader(top["card_name"])
        st.write(f'${top["reward_amount"]:,.2f} cash back' if top["unit"] == "percent_cashback"
                 else f'{top["reward_amount"]:,.0f} {top["reward_program"]}')
        if value:
            st.html(f'<div class="rp-value">${value["estimated_value_usd"]:,.2f}</div><div class="rp-note">Estimated reward value</div>')
        else:
            st.info("No configured valuation is available for this reward currency.")
        st.caption(f'{top["earn_rate"]:g}{"% cash back" if top["unit"] == "percent_cashback" else "x rewards"} on this purchase')
        st.caption("Based on your current RewardPilot valuation assumptions.")
        chart_rows = [{"Card": row["card_name"], "Estimated reward value ($)": row["reward_value"]["estimated_value_usd"],
                       "Color": "#B68A3D" if n == 0 else "#647C96"}
                      for n, row in enumerate(rows) if row.get("reward_value")]
        if chart_rows:
            st.markdown("**Your cards, compared**")
            base = alt.Chart(pd.DataFrame(chart_rows)).encode(
                y=alt.Y("Card:N", sort=None, title=None, axis=alt.Axis(labelLimit=290)),
                x=alt.X("Estimated reward value ($):Q", title="Estimated reward value ($)",
                        scale=alt.Scale(domainMax=max(r["Estimated reward value ($)"] for r in chart_rows) * 1.3 or 1)),
                tooltip=["Card:N", alt.Tooltip("Estimated reward value ($):Q", format="$.2f")])
            bars = base.mark_bar(cornerRadiusEnd=5, height=20).encode(color=alt.Color("Color:N", scale=None))
            labels = base.mark_text(align="left", dx=7, color="#203952").encode(text=alt.Text("Estimated reward value ($):Q", format="$.2f"))
            st.altair_chart((bars + labels).properties(height=150).configure_view(strokeWidth=0)
                            .configure_axis(labelColor="#47586C", titleColor="#47586C", labelFontSize=12), width="stretch")


def render_points_results(award, overall_winner=False, hotel=False):
    unit = "points" if hotel else "miles"
    with st.container(border=True, key="points_result"):
        st.html('<span class="rp-pill">POINTS OPTION</span>')
        if overall_winner:
            st.html('<span class="rp-pill rp-winner">BEST OVERALL</span>')
        st.subheader(award["target_program"])
        st.write(f'{award["required_points"]:,.0f} {unit} + ${award["taxes_fees"]:,.2f}')
        st.html(f'<div class="rp-value">{award.get("cents_per_point", 0):.2f}¢</div><div class="rp-note">Redemption value per point at your quoted price</div>')
        valuation = REWARD_VALUATIONS.get(award["target_program"]) or {}
        if valuation.get("cents_per_point") is not None and award.get("cents_per_point") is not None:
            st.caption(f'Quoted redemption: {award["cents_per_point"]:g}¢/point  ·  '
                       f'RewardPilot valuation: {valuation["cents_per_point"]:g}¢/point')
        a, b = st.columns(2)
        a.metric("Your current balance", f'{award["existing_points"]:,.0f}')
        b.metric("Points still needed" if hotel else "Miles still needed", f'{award["shortfall"]:,.0f}')
        st.progress(min(1.0, award["existing_points"] / award["required_points"]),
                    text=f'{award["required_points"]:,.0f} {unit} required')
        if award["can_book_directly"]:
            st.success("Your balance covers the quoted award.")
        else:
            options = award.get("transfer_options", [])
            for option in options:
                st.markdown(f'**{option["from_program"]} → {award["target_program"]}**')
                st.write(f'{option["required_transfer"]:,.0f} points to transfer · {option["available_points"]:,.0f} available')
                if option["can_cover_shortfall"]:
                    st.caption("Balance can cover this transfer. Review the policy checks before proceeding.")
                else:
                    st.warning("This balance does not cover the required transfer.")
            if not options:
                st.info("No supported transfer path was found for this shortfall.")


def policy_excerpts(source):
    # Quote source sentences, never manufacture cautions or policy conclusions.
    text = source["text"].split("## How RewardPilot")[0].split("## Example retrieval questions")[0]
    if text.startswith("---"):
        text = text.split("---", 2)[-1]
    lines = [line.strip().lstrip("- ") for line in text.splitlines() if line.strip() and not line.startswith("#")]
    priority = [line for line in lines if any(word in line.lower() for word in
                ("final", "availability", "excise", "$", "operated", "linked"))]
    return priority or lines[:4]


def render_smart_checks(evidence):
    if not evidence:
        return
    section("Smart Checks", "The details that make a difference.")
    for source in evidence:
        facts = " ".join(policy_excerpts(source)).lower()
        checks = []
        for phrase, label in (
            ("transfers to a partner loyalty program are final", "Transfers are final"),
            ("availability", "Confirm award availability"),
            ("excise-tax offset fee", "Transfer fee may apply"),
            ("partner-operated flights are not eligible", "Partner-operated flights are excluded"),
        ):
            if phrase in facts:
                checks.append(label)
        for label in checks or ["Review the retrieved policy conditions"]:
            st.html(f'<div class="rp-check"><span class="rp-warning-icon" aria-label="Check condition">⚠</span><strong>{escape(label)}</strong>'
                    f'<span class="rp-note">{escape(source["title"])}</span></div>')
    with st.expander("Policy details & sources"):
        for source in evidence:
            st.markdown(f'**{source["title"]}**')
            for excerpt in policy_excerpts(source):
                st.write(f"• {excerpt}")
            st.caption(f'Last verified: {source["last_verified"]}')
            url = source.get("source_url", "")
            if url.startswith("https://"):
                st.link_button("View policy source", url)


def render_results(report):
    section("RewardPilot Recommendation", "Built around your wallet.", "recommendation")
    award = report["award"] if report["inputs"]["compare_points"] else None
    overall = report.get("overall_comparison") if award else None
    if award and report.get("cash") and not overall:
        logging.getLogger(__name__).error("Missing structured overall comparison for cash and points results")
        st.warning("RewardPilot could not complete the overall cash-vs-points comparison. The individual options are shown below.")
    winner = (overall or {}).get("overall_winner")
    if (overall or {}).get("status") in ("close_call", "insufficient_data"):
        winner = overall["status"]
    winner = {"points": "use_points", "cash": "pay_cash"}.get(winner, winner)
    if overall:
        with st.container(border=True, key="overall_result_" + overall.get("status", "insufficient_data")):
            if winner in ("use_points", "pay_cash"):
                st.html('<span class="rp-overall-label">BEST OVERALL</span>')
                st.subheader("USE POINTS" if winner == "use_points" else "PAY CASH")
            else:
                status = overall.get("status")
                if status == "conditional_winner":
                    st.subheader("CONDITIONAL BEST OPTION")
                    st.write("Use Points" if overall.get("leading_option") == "points" else "Pay Cash")
                elif winner == "close_call":
                    st.subheader("CLOSE CALL")
                    lead = overall.get("leading_option")
                    st.write({"points": "Points have a slight edge",
                              "cash": "Cash currently has a slight edge"}.get(lead, "The estimated costs are equal"))
                else:
                    st.subheader("NOT ENOUGH DATA TO PICK AN OVERALL WINNER")
            advantage = overall.get("estimated_advantage_usd")
            if advantage is not None:
                label = "Estimated advantage"
                direction = {"use_points": " in favor of using points", "pay_cash": " in favor of paying cash"}.get(winner, "")
                st.write(f"{label}: ${advantage:,.2f}{direction}")
            costs = st.columns(2)
            for column, label, field in zip(costs, ["Pay cash effective cost", "Use points effective cost"],
                                             ["cash_effective_cost", "points_effective_cost"]):
                value = overall.get(field)
                if value is not None:
                    column.metric(label, f"${value:,.2f}")
            if overall.get("reason"):
                st.caption(overall["reason"].removesuffix(" Uses the quoted award unchanged and current point-value assumptions."))
            if overall.get("transfer_fee_usd"):
                st.caption(f'Included transfer fee: ${overall["transfer_fee_usd"]:,.2f}')
            for condition in overall.get("conditions", []):
                st.caption(condition)
            st.caption("Estimated costs include rewards earned or points used.")
    snapshot = report["inputs"]
    purchase_type = snapshot.get("purchase_type", "flight")
    travel = purchase_type in ("flight", "hotel")
    unit = "points" if purchase_type == "hotel" else "miles"
    st.caption(f'{purchase_type.title()} · {snapshot["merchant"]} · ${snapshot["amount"]:,.2f} · '
               f'{ui_agent.channel_label(snapshot) if travel else snapshot.get("purchase_method", "").replace("_", " ")}')
    if travel and not snapshot["booking_channel"]:
        st.info("Booking channel is unconfirmed. These results use the available earning rules; confirm your booking channel before choosing a card.")
    for notice in report["notices"]:
        st.info(notice)
    if award:
        cash_col, points_col = st.columns([1.15, 1], gap="medium")
        with cash_col:
            render_cash_results(report["cash"], winner == "pay_cash")
        with points_col:
            render_points_results(award, winner == "use_points", purchase_type == "hotel")
        top_value = report["cash"][0].get("reward_value")
        cash_copy = f'Earn ${top_value["estimated_value_usd"]:,.2f} in estimated rewards.' if top_value else "Review your card earning options."
        def cost_line(field):
            value = (overall or {}).get(field)
            return f"Effective cost: ${value:,.2f}<br>" if value is not None else ""
        cash_badge = '<span class="rp-pill">BEST OVERALL</span>' if winner == "pay_cash" else ""
        points_badge = '<span class="rp-pill">BEST OVERALL</span>' if winner == "use_points" else ""
        st.html(f'''<div class="rp-compare"><div><b>PAY CASH</b>{cash_badge}<p>{cost_line("cash_effective_cost")}{cash_copy}</p></div>
            <div><b>USE POINTS</b>{points_badge}<p>{cost_line("points_effective_cost")}
            Use {award["required_points"]:,.0f} {unit} + ${award["taxes_fees"]:,.2f}.<br>
            {"Your balance covers the quoted award." if award["can_book_directly"] else "Additional points are needed."}</p></div></div>''')
        st.caption(f'Cardholder discount status you entered: {snapshot["discount_status"]}. The quoted price was used unchanged.')
    else:
        render_cash_results(report["cash"], everyday=not travel)
    if report.get("policy_search_called") and report["evidence"]:
        render_smart_checks(report["evidence"])
    with st.expander("Why RewardPilot picked this"):
        if overall:
            summaries = {"winner": "The overall comparison favors " + {"points": "points.", "cash": "cash."}.get(overall.get("overall_winner"), "neither option."),
                         "close_call": "The overall comparison is a close call.",
                         "conditional_winner": "The leading option depends on the listed conditions.",
                         "insufficient_data": "More information is needed for an overall comparison."}
            st.write(":material/check: " + summaries.get(overall.get("status"), "Review the overall comparison above."))
        top = report["cash"][0]
        st.write(f'✓ {top["card_name"]} earns {top["earn_rate"]:g}'
                 f'{"% cash back" if top["unit"] == "percent_cashback" else "× rewards"} for this purchase.')
        if top.get("reward_value"):
            st.write("✓ It has the highest estimated reward value among your cards.")
        if award:
            if award["shortfall"]:
                st.write(f'✓ Your {award["target_program"]} balance is {award["shortfall"]:,.0f} {unit} short of this award.')
            else:
                st.write("✓ Your balance covers the quoted award.")
            for option in [item for item in award.get("transfer_options", []) if item["can_cover_shortfall"]][:1]:
                if option["can_cover_shortfall"]:
                    st.write(f'✓ Your {option["from_program"]} balance can cover the transfer shortfall, subject to the transfer conditions.')
    with st.expander("RewardPilot activity"):
        for action in report["activity"]:
            st.write(f":material/check_circle: {action}")


try:
    wallet_db.initialize_database()
    if wallet_db.get_user(1) is None:
        st.title("RewardPilot")
        st.info("Your wallet is empty. Add your cards and reward balances to start optimizing.")
        if st.button("Add cards", key="create_wallet"):
            wallet_db.initialize_user_wallet(1)
            st.rerun()
        st.stop()
    card_ids = get_user_cards(1)
    cards = [card for card_id in card_ids if (card := get_card(card_id))]
    balances = get_reward_balances(1)
except Exception:
    st.title("RewardPilot")
    st.error("Your wallet is temporarily unavailable. Please try again shortly.")
    st.stop()

render_hero(cards, balances)
render_wallet(cards, balances)
inputs, submitted = render_purchase_form()
if submitted:
    st.session_state.analysis_error = None
    if not inputs["merchant"]:
        st.session_state.analysis_error = "Enter the merchant to compare your cards."
    elif inputs["amount"] is None:
        st.session_state.analysis_error = "Enter the cash purchase amount to compare your cards."
    elif not cards:
        st.session_state.analysis_error = "An active card is needed to compare payment options."
    elif inputs["compare_points"] and (not inputs["target_program"] or
            inputs["required_points"] is None or inputs["taxes_fees"] is None):
        st.session_state.analysis_error = "Select a rewards program and enter the quoted points price and cash taxes & fees. Enter 0 if the award has no cash taxes or fees."
    else:
        with st.status("Analyzing your booking…", expanded=True) as status:
            try:
                def show_activity(label):
                    status.write(f":material/check_circle: {label}")
                    status.update(label="Building your recommendation…")
                st.session_state.analysis = ui_agent.run_analysis(inputs, on_activity=show_activity)
                status.update(label="Your recommendation is ready", state="complete", expanded=False)
            except ValueError as error:
                st.session_state.analysis_error = str(error) if str(error).startswith(("RewardPilot's", "We couldn't")) else "We couldn't finish this analysis. Please check your inputs and try again."
                status.update(label="Analysis could not finish", state="error", expanded=False)
            except Exception:
                st.session_state.analysis_error = "Our analysis service is temporarily unavailable. Your wallet is safe; please try again shortly."
                status.update(label="Analysis could not finish", state="error", expanded=False)
if st.session_state.analysis_error:
    st.error(st.session_state.analysis_error)
if st.session_state.analysis:
    if inputs != st.session_state.analysis["inputs"] or st.session_state.analysis_error:
        st.caption("Showing your last completed analysis. Select Find My Best Option to analyze the current inputs.")
    report = st.session_state.analysis
    if (report["inputs"]["compare_points"] and report.get("cash") and report.get("award")
            and "reason_code" not in (report.get("overall_comparison") or {})):
        st.session_state.analysis = ui_agent.finalize_comparison(report)
    render_results(st.session_state.analysis)
else:
    st.html('<div class="rp-empty"><b>A smarter journey starts here.</b><p>Choose your booking details above. We’ll compare your cards, points, and relevant policies.</p></div>')
with st.expander("About estimated reward values"):
    st.write("RewardPilot uses configurable point-value assumptions to compare different reward currencies. These are estimates, not guaranteed cash values.")
    for program, valuation in REWARD_VALUATIONS.items():
        if valuation and valuation.get("cents_per_point") is not None:
            st.caption(f'{program}: {valuation["cents_per_point"]:g}¢ per point')
        else:
            st.caption(f'{program}: valuation unavailable')
st.html('<div class="rp-foot">RewardPilot &bull; Smarter rewards, better decisions</div>')
