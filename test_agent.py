"""Live end-to-end demo. Prints the model-selected tool trace and final answer."""

import json
import re
import sys
from pathlib import Path

from rewardpilot_agent import create_rewardpilot_agent

QUESTION = (
    "I need to book a Delta flight that costs $1,500. The Delta award price is "
    "90,000 SkyMiles plus $33.60 in taxes. Compare paying cash with my cards "
    "versus using points and tell me my best options."
)


def test_agent():
    agent = create_rewardpilot_agent()
    result = agent.invoke(
        {"messages": [{"role": "user", "content": "My user ID is 1. " + QUESTION}]},
        config={"recursion_limit": 30},
    )
    trace = []
    outputs = {}
    for message in result["messages"]:
        for call in getattr(message, "tool_calls", []):
            trace.append({"name": call["name"], "args": call["args"]})
        if message.type == "tool":
            assert getattr(message, "status", None) != "error", message.content
            outputs.setdefault(message.name, []).append(json.loads(message.content))
    answer = result["messages"][-1].content
    report = {"question": QUESTION, "tool_calls": trace,
              "tool_results": outputs, "final_answer": answer}
    # Keep the complete run reviewable without replaying paid API calls.
    Path("agent_test_output.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print("TOOL-CALL SEQUENCE")
    for number, call in enumerate(trace, 1):
        print(f'{number}. {call["name"]} {json.dumps(call["args"])}')
    print("\nFINAL AGENT ANSWER\n")
    print(answer)

    assert set(outputs) >= {"get_rewards_wallet", "compare_cash_payment",
                            "evaluate_points_redemption", "search_rewards_policy"}
    wallet = outputs["get_rewards_wallet"][0]
    assert set(wallet["card_ids"]) == {
        "delta_platinum_amex", "amex_gold", "chase_sapphire_preferred"}
    cash = outputs["compare_cash_payment"][0]
    assert cash[0]["card_id"] == "amex_gold"
    assert [row["reward_amount"] for row in cash] == [4500, 4500, 3000]
    assert [row["reward_value"]["estimated_value_usd"] for row in cash] == [67.5, 54, 45]
    award = outputs["evaluate_points_redemption"][-1]
    assert award["required_points"] == 90000
    assert award["existing_points"] == 50000
    assert award["shortfall"] == 40000
    assert award["cents_per_point"] == 1.63
    assert not award["can_book_directly"]
    assert any(row["from_program"] == "Amex Membership Rewards"
               and row["required_transfer"] == 40000
               and row["can_cover_shortfall"] for row in award["transfer_options"])
    evidence = [row for batch in outputs["search_rewards_policy"] for row in batch]
    policy_filters = {(call["args"].get("program"), call["args"].get("policy_type"))
                      for call in trace if call["name"] == "search_rewards_policy"}
    assert {("Amex Membership Rewards", "transfer_policy"),
            ("Delta SkyMiles", "award_discount")} <= policy_filters
    assert any("takeoff" in row["source_file"].lower() for row in evidence)
    assert "CASH" in answer.upper() and "POINTS" in answer.upper()
    assert "direct" in answer.lower(), "Missing direct-booking assumption"
    assert any(row["last_verified"] in answer for row in evidence), "Missing policy date citation"
    assert "takeoff" in answer.lower() or "takeoff 15" in answer.lower()
    assert "operated" in answer.lower(), "Missing operating-carrier eligibility condition"
    for amount in ("90000", "50000", "40000"):
        assert amount in answer.replace(",", ""), "Missing award cost, balance or shortfall"
    assert any("transfer" in call["args"].get("question", "").lower()
               for call in trace if call["name"] == "search_rewards_policy"), "Missing transfer policy check"
    allowed_dollars = {1500, 33.6, 67.5, 54, 45}
    # Policy evidence can legitimately supply fee amounts, not just calculations.
    for row in evidence:
        allowed_dollars.update(float(value.replace(",", ""))
            for value in re.findall(r"\$([\d,]+(?:\.\d+)?)", row["text"]))
    for value in re.findall(r"\$([\d,]+(?:\.\d+)?)", answer):
        assert float(value.replace(",", "")) in allowed_dollars, "Unsupported dollar calculation"
    print("\nPASS: Agent tool routing and deterministic demo results")
    print("Full trace saved to agent_test_output.json; review prose for policy conditions.")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    test_agent()
