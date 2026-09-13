"""Offline retrieval and wrapper regression tests; no API credentials needed."""

from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import agent_tools
import rag_retriever
from rag_answer import build_context


class AgentComponentTests(unittest.TestCase):
    def test_retrieval_threshold_deduplication_and_metadata(self):
        def match(source, score):
            return SimpleNamespace(score=score, metadata={
                "source_file": source, "title": source, "text": "Policy text",
                "source_url": "https://example.com", "last_verified": "2026-09-12"})
        nebius, index = Mock(), Mock()
        nebius.embeddings.create.return_value.data = [SimpleNamespace(embedding=[0.1])]
        index.query.return_value.matches = [match("a", .9), match("a", .85),
                                            match("b", .55), match("c", .54)]
        with patch.object(rag_retriever, "_clients", return_value=(nebius, index)):
            evidence = rag_retriever.retrieve_policy_context("question")
            self.assertEqual([row["source_file"] for row in evidence], ["a", "b"])
            self.assertIn("Last verified: 2026-09-12", build_context(evidence))
            self.assertEqual(len(rag_retriever.retrieve_policy_context("question", 1)), 1)
            index.query.return_value.matches = [match("c", .54)]
            self.assertEqual(rag_retriever.retrieve_policy_context("question"), [])
        nebius.chat.completions.create.assert_not_called()
        self.assertEqual(index.query.call_args.kwargs["namespace"], "rewardpilot-policies")

    def test_cash_wrapper_delegates_without_recalculating(self):
        with patch.object(agent_tools, "get_user_cards", return_value=["amex_gold"]) as wallet, \
             patch.object(agent_tools, "compare_cash_cards", return_value=[{"sentinel": 1}]) as engine:
            result = agent_tools.compare_cash_payment.invoke({"user_id": 1, "amount": 1500,
                "purchase_type": "flight", "merchant": "Delta", "booking_channel": "direct"})
        wallet.assert_called_once_with(1)
        engine.assert_called_once_with(["amex_gold"], 1500,
            {"type": "flight", "merchant": "Delta", "booking_channel": "direct"})
        self.assertEqual(result, [{"sentinel": 1}])

    def test_award_wrapper_delegates_without_recalculating(self):
        balances = {"Delta SkyMiles": 50000}
        with patch.object(agent_tools, "get_reward_balances", return_value=balances), \
             patch.object(agent_tools, "evaluate_award_option", return_value={"sentinel": 2}) as engine:
            result = agent_tools.evaluate_points_redemption.invoke({"user_id": 1,
                "target_program": "Delta SkyMiles", "required_points": 90000,
                "cash_price": 1500, "taxes_fees": 33.6})
        engine.assert_called_once_with("Delta SkyMiles", 90000, 33.6, 1500, balances)
        self.assertEqual(result, {"sentinel": 2})

    def test_policy_tool_returns_evidence_only(self):
        with patch.object(agent_tools, "retrieve_policy_context", return_value=[]) as retrieve:
            self.assertEqual(agent_tools.search_rewards_policy.invoke({"question": "policy?"}), [])
        retrieve.assert_called_once_with("policy?", program=None, policy_type=None)

    def test_filter_combinations(self):
        nebius, index = Mock(), Mock()
        nebius.embeddings.create.return_value.data = [SimpleNamespace(embedding=[0.1])]
        index.query.return_value.matches = []
        for kwargs, expected in [
            ({}, None),
            ({"program": "Delta SkyMiles"}, {"program": {"$eq": "Delta SkyMiles"}}),
            ({"policy_type": "award_discount"}, {"policy_type": {"$eq": "award_discount"}}),
            ({"program": "Delta SkyMiles", "policy_type": "award_discount"},
             {"program": {"$eq": "Delta SkyMiles"}, "policy_type": {"$eq": "award_discount"}}),
        ]:
            with self.subTest(kwargs=kwargs), patch.object(rag_retriever, "_clients", return_value=(nebius, index)):
                self.assertEqual(rag_retriever.retrieve_policy_context("question", **kwargs), [])
                self.assertEqual(index.query.call_args.kwargs.get("filter"), expected)
                if expected is None:
                    self.assertNotIn("filter", index.query.call_args.kwargs)

    def test_policy_tool_passes_filters(self):
        with patch.object(agent_tools, "retrieve_policy_context", return_value=[]) as retrieve:
            agent_tools.search_rewards_policy.invoke({"question": "policy?",
                "program": "Delta SkyMiles", "policy_type": "award_discount"})
        retrieve.assert_called_once_with("policy?", program="Delta SkyMiles", policy_type="award_discount")

    def test_unknown_program_requests_correction(self):
        with patch.object(agent_tools, "get_reward_balances", return_value={}), \
             patch.object(agent_tools, "evaluate_award_option") as engine:
            result = agent_tools.evaluate_points_redemption.invoke({"user_id": 1,
                "target_program": "Delta", "required_points": 90000,
                "cash_price": 1500, "taxes_fees": 33.6})
        self.assertIn("error", result)
        self.assertIn("Delta SkyMiles", result["supported_programs"])
        engine.assert_not_called()


if __name__ == "__main__":
    unittest.main(verbosity=2)
