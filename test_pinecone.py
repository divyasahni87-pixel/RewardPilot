"""Live retrieval smoke test using the shared retriever (no chat call)."""
import json
from rag_retriever import MIN_SCORE, retrieve_policy_context


def test_policy_retrieval():
    evidence = retrieve_policy_context("Delta TakeOff 15 eligibility Delta-operated award tickets")
    assert evidence, "No relevant policy evidence retrieved"
    assert len({row["source_file"] for row in evidence}) == len(evidence)
    assert all(row["score"] >= MIN_SCORE for row in evidence)
    assert any("takeoff" in row["source_file"].lower() for row in evidence)
    print(json.dumps(evidence, indent=2))
    print("PASS: Live Nebius embedding and Pinecone policy retrieval")


if __name__ == "__main__":
    test_policy_retrieval()
