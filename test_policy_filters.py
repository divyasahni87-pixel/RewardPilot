"""Live metadata-filter regression tests against the policy namespace."""

from rag_retriever import retrieve_policy_context


def test_policy_filters():
    cases = [
        ("Is an Amex Membership Rewards transfer to Delta reversible?",
         "Amex Membership Rewards", "transfer_policy", "amex_delta_transfer_policy.md"),
        ("Can I use TakeOff 15 on a partner-operated flight?",
         "Delta SkyMiles", "award_discount", "delta_takeoff15.md"),
        ("Does Amex Platinum get 5X on hotels booked directly?",
         "Amex Membership Rewards", "earning_rule", "amex_platinum_air_hotel_policy.md"),
    ]
    for question, program, policy_type, source in cases:
        rows = retrieve_policy_context(question, program=program, policy_type=policy_type)
        assert rows and rows[0]["source_file"] == source, rows
        assert all(row["program"] == program and row["policy_type"] == policy_type for row in rows)
        print(f'PASS: {source} ranks #1 (score={rows[0]["score"]:.6f})')
    # This deliberately mismatched combination has no candidate documents.
    rows = retrieve_policy_context(cases[0][0], program="Amex Membership Rewards",
                                   policy_type="award_discount")
    assert rows == [], rows
    print("PASS: Wrong filter returns no documents; no unfiltered fallback.")


if __name__ == "__main__":
    test_policy_filters()
