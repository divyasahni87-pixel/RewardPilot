"""Live UI-adapter audit; captures only public answers and tool messages."""
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
from ui_agent import run_analysis
from rewardpilot_agent import create_rewardpilot_agent
from decision_engine import compare_cash_cards, evaluate_award_option
from wallet_db import get_user_cards, get_reward_balances


class RecordingAgent:
    def __init__(self):
        self.agent = create_rewardpilot_agent()
        self.calls = []
        self.results = []
        self.answer = ""

    def stream(self, *args, **kwargs):
        for update in self.agent.stream(*args, **kwargs):
            for node in update.values():
                if not isinstance(node, dict):
                    continue
                for message in node.get("messages", []):
                    for call in getattr(message, "tool_calls", []):
                        self.calls.append({"id": call["id"], "name": call["name"], "args": call["args"]})
                    if message.type == "tool":
                        try:
                            content = json.loads(message.content)
                        except (ValueError, TypeError):
                            content = message.content
                        self.results.append({"call_id": message.tool_call_id, "name": message.name,
                            "status": getattr(message, "status", "success"), "result": content})
                    elif message.type == "ai" and not getattr(message, "tool_calls", []):
                        self.answer = message.content
            yield update


def run_scenario(number, inputs):
    recorder = RecordingAgent()
    record = {"scenario": number, "inputs": inputs, "adapter_error": None}
    try:
        record["ui_result"] = run_analysis(inputs, agent=recorder)
    except Exception as error:
        record["adapter_error"] = f"{type(error).__name__}: {error}"
    record.update(tool_calls=recorder.calls, tool_results=recorder.results, final_answer=recorder.answer)
    record["raw_model_answer"] = recorder.answer
    record["final_answer"] = record.get("ui_result", {}).get("answer", "")
    cards, balances = get_user_cards(1), get_reward_balances(1)
    cash = compare_cash_cards(cards, inputs["amount"], {"type": "flight", "merchant": inputs["merchant"],
                                                      "booking_channel": inputs["booking_channel"]})
    award = evaluate_award_option(inputs["target_program"], inputs["required_points"], inputs["taxes_fees"],
                                  inputs["amount"], balances) if inputs["compare_points"] else None
    record["expected_cash"] = cash
    record["expected_award"] = award
    ui = record.get("ui_result", {})
    record["presentation_matches"] = bool(ui) and f'${cash[0]["reward_value"]["estimated_value_usd"]:,.2f}' in ui["answer"]
    if not inputs["compare_points"] and ui:
        record["presentation_matches"] = record["presentation_matches"] and not any(
            word in ui["answer"].lower() for word in ("award", "takeoff", "transfer", "compare_points", "policy"))
        record["presentation_matches"] = record["presentation_matches"] and [c["name"] for c in recorder.calls] == ["get_rewards_wallet", "compare_cash_payment"]
    record["cash_matches_engine"] = ui.get("cash") == cash
    record["award_matches_engine"] = ui.get("award") == award
    record["unexpected_award_call"] = not inputs["compare_points"] and any(c["name"] == "evaluate_points_redemption" for c in recorder.calls)
    print(f"Scenario {number}: adapter_error={record['adapter_error']}; cash_matches={record['cash_matches_engine']}; award_matches={record['award_matches_engine']}", flush=True)
    return record


def test_scenarios():
    base = {"merchant": "Delta", "amount": 1500.0, "booking_channel": "direct", "compare_points": True,
            "target_program": "Delta SkyMiles", "required_points": 90000, "taxes_fees": 33.6,
            "discount_status": "I'm not sure"}
    scenarios = [base, {**base, "compare_points": False, "required_points": None, "taxes_fees": None,
                        "discount_status": None}, {**base, "booking_channel": ""}]
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = [executor.submit(run_scenario, i, inputs) for i, inputs in enumerate(scenarios, 1)]
        reports = [future.result() for future in futures]
    Path("ui_live_results.json").write_text(json.dumps(reports, indent=2, ensure_ascii=False), encoding="utf-8")
    assert all(r["cash_matches_engine"] and r["award_matches_engine"] and not r["adapter_error"]
               and not r["unexpected_award_call"] and r["presentation_matches"] for r in reports), "See ui_live_results.json for failures"


if __name__ == "__main__":
    test_scenarios()
