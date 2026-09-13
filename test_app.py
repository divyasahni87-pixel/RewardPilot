"""UI interaction tests use recorded-style tool messages, never paid API calls."""

import json
from pathlib import Path
import unittest
from unittest.mock import patch

from langchain_core.messages import AIMessage, ToolMessage
from streamlit.testing.v1 import AppTest

import ui_agent
from decision_engine import compare_cash_cards, evaluate_award_option
from wallet_db import get_user_cards, get_reward_balances


class ToolMessageAgent:
    def __init__(self, inputs):
        self.inputs = inputs

    def stream(self, request, **kwargs):
        inputs = self.inputs
        cards, balances = get_user_cards(1), get_reward_balances(1)
        calls = [("get_rewards_wallet", {"user_id": 1}, {"card_ids": cards, "reward_balances": balances})]
        args = {"user_id": 1, "amount": inputs["amount"], "merchant": inputs["merchant"],
                "purchase_type": inputs.get("purchase_type", "flight"), "booking_channel": inputs["booking_channel"],
                **{key: inputs[key] for key in ui_agent.PURCHASE_DETAILS if key in inputs}}
        calls.append(("compare_cash_payment", args, compare_cash_cards(cards, inputs["amount"],
            {"type": inputs.get("purchase_type", "flight"), "merchant": inputs["merchant"], "booking_channel": inputs["booking_channel"],
             **{key: inputs[key] for key in ui_agent.PURCHASE_DETAILS if key in inputs}})))
        if inputs["compare_points"]:
            args = {"user_id": 1, "target_program": inputs["target_program"], "required_points": inputs["required_points"],
                    "cash_price": inputs["amount"], "taxes_fees": inputs["taxes_fees"]}
            calls.append(("evaluate_points_redemption", args, evaluate_award_option(
                inputs["target_program"], inputs["required_points"], inputs["taxes_fees"], inputs["amount"], balances)))
        if inputs["compare_points"]:
            calls.append(("search_rewards_policy", {"question": "policy"}, []))
        for number, (name, args, result) in enumerate(calls):
            yield {"model": {"messages": [AIMessage(content="", tool_calls=[
                {"id": str(number), "name": name, "args": args}])]}}
            yield {"tools": {"messages": [ToolMessage(content=json.dumps(result), name=name, tool_call_id=str(number))]}}
        yield {"model": {"messages": [AIMessage(content="Your card comparison is ready.",
            additional_kwargs={"reasoning_content": "PRIVATE MODEL REASONING"})]}}


original_run = ui_agent.run_analysis


def offline_run(inputs, on_activity=None):
    return original_run(inputs, on_activity, agent=ToolMessageAgent(inputs))


class AppTests(unittest.TestCase):
    def app(self):
        return AppTest.from_file("app.py", default_timeout=40).run()

    def test_wallet_balances_stay_with_cards_and_award_panel_is_optional(self):
        app = self.app()
        groups = [item.proto.body for item in app.get("html") if 'class="rp-wallet-group"' in item.proto.body]
        self.assertEqual(len(groups), len(get_user_cards(1)))
        for program, balance in get_reward_balances(1).items():
            group = next((body for body in groups if program in body), None)
            if group is None:
                self.assertTrue(any(program in item.value and f"{balance:,.0f}" in item.value for item in app.caption))
                continue
            self.assertIn(f"{balance:,.0f}", group)
            self.assertIn("Program balance", group)
        self.assertNotIn("**Compare with a points option**", [item.value for item in app.markdown])
        app.toggle(key="compare_points").set_value(True).run()
        self.assertIn("**Compare with a points option**", [item.value for item in app.markdown])
        self.assertIsNone(app.number_input(key="required_points").value)
        self.assertIsNone(app.number_input(key="taxes_fees").value)

    def test_empty_award_inputs_and_validation(self):
        with patch.object(ui_agent, "run_analysis", side_effect=offline_run) as run:
            app = self.app()
            self.assertFalse(app.toggle(key="compare_points").value)
            self.assertNotIn("required_points", [item.key for item in app.number_input])
            app.toggle(key="compare_points").set_value(True).run()
            self.assertIsNone(app.selectbox(key="target_program").value)
            self.assertIsNone(app.number_input(key="required_points").value)
            self.assertIsNone(app.number_input(key="taxes_fees").value)
            self.assertNotIn("discount_status", [item.key for item in app.selectbox])
            app.button(key="find").click().run()
            self.assertTrue(app.error)
            run.assert_not_called()
            app.selectbox(key="target_program").select("Delta SkyMiles").run()
            app.number_input(key="required_points").set_value(90000).run()
            self.assertEqual(app.selectbox(key="discount_status").value, "I'm not sure")
            app.button(key="find").click().run()
            run.assert_not_called()
            app.number_input(key="taxes_fees").set_value(0.0).run()
            app.button(key="find").click().run()
            self.assertFalse(app.exception)
            self.assertEqual(run.call_count, 1)
            self.assertEqual(app.session_state["analysis"]["award"]["taxes_fees"], 0)

    def test_example_inputs(self):
        with patch.object(ui_agent, "run_analysis") as run:
            app = self.app()
            app.button(key="example").click().run()
            self.assertFalse(app.exception)
            self.assertTrue(app.toggle(key="compare_points").value)
            self.assertEqual(app.selectbox(key="target_program").value, "Delta SkyMiles")
            self.assertEqual(app.number_input(key="required_points").value, 90000)
            self.assertEqual(app.number_input(key="taxes_fees").value, 33.60)
            self.assertEqual(app.number_input(key="amount").value, 1500)
            self.assertEqual(app.text_input(key="merchant").value, "Delta")
            self.assertEqual(app.selectbox(key="channel").value, "Direct with airline")
            self.assertEqual(app.selectbox(key="discount_status").value, "I'm not sure")
            run.assert_not_called()

    def test_award_and_persistent_results(self):
        with patch.object(ui_agent, "run_analysis", side_effect=offline_run) as run:
            app = self.app()
            app.button(key="example").click().run()
            self.assertFalse(app.exception)
            app.button(key="find").click().run()
            self.assertFalse(app.exception)
            result = app.session_state["analysis"]
            self.assertEqual(result["cash"][0]["reward_value"]["estimated_value_usd"], 67.5)
            self.assertEqual(result["award"]["shortfall"], 40000)
            self.assertIn("$67.50", result["answer"])
            self.assertTrue(any("Quoted redemption: 1.63¢/point" in item.value and
                                "RewardPilot valuation: 1.2¢/point" in item.value for item in app.caption))
            why = next(item for item in app.expander if item.label == "Why RewardPilot picked this")
            summary = " ".join(item.value for item in why.markdown)
            self.assertNotIn("Your assistant", summary)
            self.assertIn("40,000", summary)
            self.assertFalse(any("Smart Checks" in element.proto.body for element in app.get("html")))
            app.number_input(key="amount").set_value(1600).run()
            self.assertEqual(run.call_count, 1)
            self.assertEqual(app.session_state["analysis"]["inputs"]["amount"], 1500)
            self.assertNotIn("PRIVATE MODEL REASONING", str(app))

    def test_cash_only(self):
        with patch.object(ui_agent, "run_analysis", side_effect=offline_run):
            app = self.app()
            app.toggle(key="compare_points").set_value(False).run()
            self.assertNotIn("required_points", [element.key for element in app.number_input])
            app.button(key="find").click().run()
            self.assertFalse(app.exception)
            self.assertIsNone(app.session_state["analysis"]["award"])
            self.assertNotIn("overall_comparison", app.session_state["analysis"])
            self.assertFalse(any("BEST OVERALL" in item.value for item in app.subheader))
            self.assertNotIn("BEST OVERALL", " ".join(item.proto.body for item in app.get("html")))
            result = app.session_state["analysis"]
            self.assertEqual([call["name"] for call in result["tool_calls"]],
                             ["get_rewards_wallet", "compare_cash_payment"])
            for forbidden in ("award", "takeoff", "transfer", "compare_points", "policy", "BEST POINTS"):
                self.assertNotIn(forbidden.lower(), result["answer"].lower())
            self.assertIn("$67.50", result["answer"])
            self.assertFalse(app.info)

    def test_overall_banner(self):
        import decision_engine
        for points, winner, label in ((4500, "points", "USE POINTS"),
                                       (45000, "cash", "PAY CASH"),
                                       (39000, None, "CLOSE CALL")):
            with self.subTest(points=points), patch.object(ui_agent, "run_analysis", side_effect=offline_run):
                app = self.app()
                app.button(key="example").click().run()
                app.number_input(key="amount").set_value(450 if points == 4500 else 500).run()
                app.number_input(key="required_points").set_value(points).run()
                app.number_input(key="taxes_fees").set_value(10.0).run()
                app.button(key="find").click().run()
                self.assertFalse(app.exception)
                result = app.session_state["analysis"]
                self.assertEqual(result["overall_comparison"]["overall_winner"], winner)
                self.assertIn(label, [item.value for item in app.subheader])
                html = " ".join(item.proto.body for item in app.get("html"))
                self.assertIn("BEST CASH CARD", html)
                self.assertIn("POINTS OPTION", html)
                if winner is None:
                    self.assertNotIn("BEST OVERALL", html)
                else:
                    self.assertEqual(html.count("BEST OVERALL"), 3)
                if points == 4500:
                    self.assertEqual(result["cash"][0]["card_id"], "amex_gold")
                    self.assertIn("$429.75", [item.value for item in app.metric])
                    self.assertIn("$64.00", [item.value for item in app.metric])
                    self.assertEqual(result["overall_comparison"]["cash_effective_cost"], 429.75)
                    self.assertEqual(result["overall_comparison"]["points_effective_cost"], 64)
                    self.assertIn("Estimated advantage: $365.75 in favor of using points", " ".join(item.value for item in app.markdown))
                    self.assertIn("Effective cost: $429.75", html)
                    self.assertIn("Effective cost: $64.00", html)
                    # First result label is cash; winning badge follows the points label.
                    cash_html = html.split("BEST CASH CARD", 1)[1].split("POINTS OPTION", 1)[0]
                    self.assertNotIn("BEST OVERALL", cash_html)
                    self.assertIn("BEST OVERALL", html.split("POINTS OPTION", 1)[1])
                elif winner == "cash":
                    self.assertIn("BEST OVERALL", html.split("BEST CASH CARD", 1)[1].split("POINTS OPTION", 1)[0])
        with patch.object(ui_agent, "run_analysis", side_effect=offline_run), patch.dict(
                decision_engine.REWARD_VALUATIONS, {"Delta SkyMiles": {}}):
            app = self.app()
            app.button(key="example").click().run()
            app.button(key="find").click().run()
            self.assertFalse(app.exception)
            self.assertIn("NOT ENOUGH DATA TO PICK AN OVERALL WINNER", [item.value for item in app.subheader])
            self.assertNotIn("BEST OVERALL", " ".join(item.proto.body for item in app.get("html")))

    def test_legacy_session_restores_structured_comparison(self):
        inputs = {"merchant": "Delta", "amount": 450, "booking_channel": "direct",
                  "compare_points": True, "target_program": "Delta SkyMiles",
                  "required_points": 4500, "taxes_fees": 10, "discount_status": "I'm not sure"}
        report = offline_run(inputs)
        del report["overall_comparison"]
        report["answer"] = "Untrusted stale prose: cash wins by $999."
        with patch.object(ui_agent, "run_analysis") as agent:
            app = self.app()
            app.session_state["analysis"] = report
            app.run()
            self.assertFalse(app.exception)
            agent.assert_not_called()
            restored = app.session_state["analysis"]
            self.assertEqual(restored["overall_comparison"]["estimated_advantage_usd"], 365.75)
            self.assertIn("USE POINTS", [item.value for item in app.subheader])
            self.assertNotIn("$999", " ".join(item.value for item in app.markdown))

    def test_old_transfer_result_is_recomputed_before_rendering(self):
        inputs = {"merchant": "Delta", "amount": 823.01, "booking_channel": "direct",
                  "compare_points": True, "target_program": "Delta SkyMiles",
                  "required_points": 60000, "taxes_fees": 10, "discount_status": "I'm not sure"}
        report = offline_run(inputs)
        report["overall_comparison"] = {"status": "insufficient_data", "leading_option": None,
            "cash_effective_cost": 785.97, "points_effective_cost": 760}
        with patch.object(ui_agent, "run_analysis") as agent:
            app = self.app()
            app.session_state["analysis"] = report
            app.run()
            agent.assert_not_called()
            self.assertFalse(app.exception)
            self.assertIn("CLOSE CALL", [item.value for item in app.subheader])
            result = app.session_state["analysis"]["overall_comparison"]
            self.assertEqual(result["reason_code"], "close_call_points")
            self.assertEqual(result["points_effective_cost"], 766)
            self.assertNotIn("close_call_points", " ".join(item.value for item in app.markdown))

    def test_missing_comparison_in_new_result_is_recovered(self):
        def incomplete(inputs, on_activity=None):
            report = offline_run(inputs, on_activity)
            del report["overall_comparison"]
            return report
        with patch.object(ui_agent, "run_analysis", side_effect=incomplete):
            app = self.app()
            app.button(key="example").click().run()
            app.button(key="find").click().run()
            self.assertFalse(app.exception)
            self.assertIsNotNone(app.session_state["analysis"]["overall_comparison"])

    def test_overall_failure_warns_without_hiding_individual_options(self):
        with patch.object(ui_agent, "run_analysis", side_effect=offline_run), patch(
                "decision_engine.compare_payment_options", side_effect=RuntimeError("injected failure")):
            app = self.app()
            app.button(key="example").click().run()
            with self.assertLogs(level="ERROR") as logs:
                app.button(key="find").click().run()
            self.assertFalse(app.exception)
            self.assertTrue(any("overall comparison" in line for line in logs.output))
            self.assertIn("RewardPilot could not complete the overall cash-vs-points comparison. The individual options are shown below.",
                          [item.value for item in app.warning])
            html = " ".join(item.proto.body for item in app.get("html"))
            self.assertIn("BEST CASH CARD", html)
            self.assertIn("POINTS OPTION", html)
            self.assertNotIn("BEST OVERALL", html)

    def test_transfer_close_call_and_conditional_banner(self):
        for amount, heading in ((823.01, "CLOSE CALL"), (1500, "CONDITIONAL BEST OPTION")):
            with self.subTest(amount=amount), patch.object(ui_agent, "run_analysis", side_effect=offline_run):
                app = self.app()
                app.button(key="example").click().run()
                app.number_input(key="amount").set_value(amount).run()
                app.number_input(key="required_points").set_value(60000).run()
                app.number_input(key="taxes_fees").set_value(10.0).run()
                app.button(key="find").click().run()
                self.assertFalse(app.exception)
                self.assertIn(heading, [item.value for item in app.subheader])
                self.assertNotIn("NOT ENOUGH DATA", " ".join(item.value for item in app.subheader))
                if amount == 823.01:
                    self.assertIn("Points have a slight edge", [item.value for item in app.markdown])
                    self.assertIn("Estimated advantage: $19.97", [item.value for item in app.markdown])
                    self.assertIn("$766.00", [item.value for item in app.metric])

    def test_policy_details_are_collapsed_and_sourced(self):
        def with_evidence(inputs, on_activity=None):
            result = offline_run(inputs, on_activity)
            result["evidence"] = [{"title": "Amex transfer policy", "last_verified": "2026-09-12",
                "source_url": "https://global.americanexpress.com/rewards/transfer?rfs=1",
                "text": Path("rag_docs/amex_delta_transfer_policy.md").read_text(encoding="utf-8")}]
            return result
        with patch.object(ui_agent, "run_analysis", side_effect=with_evidence):
            app = self.app()
            app.button(key="example").click().run()
            app.button(key="find").click().run()
            self.assertFalse(app.exception)
            details = next(item for item in app.expander if item.label == "Policy details & sources")
            self.assertFalse(details.proto.expanded)
            text = " ".join(item.value for item in details.markdown)
            for fact in ("are final", "$0.0006", "$99", "availability"):
                self.assertIn(fact, text)
            self.assertNotIn("Example retrieval", text)
            main_html = " ".join(item.proto.body for item in app.get("html"))
            self.assertNotIn("$0.0006", main_html)

    def test_unknown_channel(self):
        with patch.object(ui_agent, "run_analysis", side_effect=offline_run):
            app = self.app()
            app.selectbox(key="channel").select("Other / Not sure").run()
            app.button(key="find").click().run()
            self.assertFalse(app.exception)
            result = app.session_state["analysis"]
            self.assertEqual(result["inputs"]["booking_channel"], "")
            self.assertEqual(result["cash"][0]["card_id"], "chase_sapphire_preferred")

    def test_chase_travel_1250(self):
        with patch.object(ui_agent, "run_analysis", side_effect=offline_run):
            app = self.app()
            app.selectbox(key="channel").select("Chase Travel").run()
            app.number_input(key="amount").set_value(1250).run()
            app.toggle(key="compare_points").set_value(False).run()
            app.button(key="find").click().run()
            self.assertFalse(app.exception)
            result = app.session_state["analysis"]
            self.assertEqual(result["cash"][0]["card_id"], "chase_sapphire_preferred")
            self.assertIn("$93.75", result["answer"])
            self.assertIn("Booking channel: Chase Travel", result["answer"])
            self.assertNotIn("direct", result["answer"].lower())

    def test_friendly_service_failure(self):
        with patch.object(ui_agent, "run_analysis", side_effect=RuntimeError("SECRET API ERROR")):
            app = self.app()
            app.button(key="find").click().run()
            self.assertFalse(app.exception)
            self.assertTrue(app.error)
            self.assertNotIn("SECRET API ERROR", app.error[0].value)

    def test_missing_keys(self):
        with patch.dict("os.environ", {"NEBIUS_API_KEY": "", "PINECONE_API_KEY": ""}):
            with self.assertRaisesRegex(ValueError, "not configured"):
                original_run({})


if __name__ == "__main__":
    unittest.main(verbosity=2)
