"""Live regression checks for full-document policy retrieval."""

from pathlib import Path

from rag_retriever import retrieve_policy_context


def test_full_policy_retrieval():
    queries = [
        ("Is an Amex Membership Rewards transfer to Delta reversible?",
         "amex_delta_transfer_policy.md"),
        ("Is there a fee to transfer Amex Membership Rewards points to Delta SkyMiles?",
         "amex_delta_transfer_policy.md"),
        ("Can I use TakeOff 15 on a partner-operated flight?", "delta_takeoff15.md"),
    ]
    for question, source in queries:
        evidence = retrieve_policy_context(question)
        assert evidence, question
        top = evidence[0]
        assert top["source_file"] == source, [(r["source_file"], r["score"]) for r in evidence]
        original = (Path(__file__).resolve().parent / "rag_docs" / source).read_text(encoding="utf-8")
        assert top["text"] == original, "Returned evidence must contain the complete document"
        if source == "amex_delta_transfer_policy.md":
            for fact in ("Transfers to a partner loyalty program are final.",
                         "should be checked before transferring points", "excise-tax offset fee",
                         "$0.0006 per point transferred", "Maximum fee: $99"):
                assert fact in top["text"], fact
        else:
            assert "Partner-operated flights are not eligible." in top["text"]
        print(f"Query: {question}")
        print(f"Rank #1: {source} | score={top['score']:.6f}")
        print("PASS: Complete document and relevant policy facts returned.\n")


if __name__ == "__main__":
    test_full_policy_retrieval()
