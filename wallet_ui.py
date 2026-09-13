"""Manual wallet editing; card definitions remain in the JSON catalog."""
import sqlite3

import streamlit as st

from decision_engine import CARDS
import wallet_db as db


def wallet_changed(message="Wallet updated.", *, keep_open=False):
    st.session_state.wallet_editor_open = keep_open
    st.session_state.analysis = None
    st.session_state.analysis_error = None
    st.session_state.wallet_notice = message
    # Card changes rebuild the program list without discarding balance drafts.
    # Saving closes the editor and resets drafts to the newly persisted values.
    if not keep_open:
        clear_balance_drafts()
    st.rerun()


def close_wallet():
    st.session_state.wallet_editor_open = False
    clear_balance_drafts()


def clear_balance_drafts():
    for key in list(st.session_state):
        if key.startswith("wallet_balance_"):
            del st.session_state[key]


@st.dialog("Manage Wallet", width="large", on_dismiss=close_wallet)
def manage_wallet(user_id=1):
    try:
        if db.get_user(user_id) is None:
            st.info("Your wallet needs to be set up before you can edit it.")
            return
        active = db.get_user_cards(user_id)
        balances = db.get_reward_balances(user_id)
        catalog = {card["card_id"]: card for card in CARDS}
        if st.session_state.get("wallet_notice"):
            st.success(st.session_state.pop("wallet_notice"))
        st.caption("Card changes are saved immediately. Reward balances are saved when you click Save balances.")
        with st.container(border=True, key="wallet_add_section"):
            st.subheader("Add a card")
            issuer = st.selectbox("Issuer", sorted({card["issuer"] for card in CARDS}), key="wallet_issuer")
            options = [card["card_id"] for card in CARDS if card["issuer"] == issuer]
            card_id = st.selectbox("Card", options, format_func=lambda key: catalog[key]["card_name"],
                                   key="wallet_card")
            if st.button("Add card", key="wallet_add", type="secondary", icon=":material/add:"):
                if card_id in active:
                    st.info("This card is already in your wallet.")
                else:
                    db.add_user_card(user_id, card_id)
                    wallet_changed("Card added", keep_open=True)
        st.subheader("Your cards")
        if not active:
            st.caption("Your wallet is empty. Add your cards and reward balances to start optimizing.")
        for owned_id in active:
            card = catalog.get(owned_id)
            with st.container(border=True, key="wallet_owned_" + owned_id):
                text, action = st.columns([4, 1], vertical_alignment="center")
                text.markdown("**" + (card["card_name"] if card else "Unrecognized saved card") + "**")
                if card:
                    text.caption(card["reward_program"])
                if action.button("Remove", key="wallet_remove_" + owned_id, type="secondary"):
                    db.set_card_active(user_id, owned_id, False)
                    wallet_changed("Card removed", keep_open=True)
        programs = sorted({catalog[key]["reward_program"] for key in active if key in catalog})
        other = sorted(set(balances) - set(programs))
        with st.form("wallet_balances"):
            st.subheader("Reward balances")
            st.caption("One balance per program, shared by all cards that earn it.")
            updates = {}
            for group, names in (("", programs), ("Other reward balances", other)):
                if names and group:
                    st.markdown(f"**{group}**")
                for program in names:
                    with st.container(border=True):
                        label, entry = st.columns([3, 2], vertical_alignment="center")
                        label.markdown(f"**{program}**")
                        updates[program] = entry.number_input(program, min_value=0.0,
                            value=float(balances.get(program, 0)), step=1000.0,
                            key="wallet_balance_" + program, label_visibility="collapsed")
            if st.form_submit_button("Save balances", disabled=not updates, type="primary", width="stretch"):
                db.save_reward_balances(user_id, updates)
                wallet_changed()
        if st.button("Done", key="wallet_done"):
            close_wallet()
            st.rerun()
    except (ValueError, sqlite3.Error):
        st.error("We couldn't save your wallet. Check your entries and try again.")
