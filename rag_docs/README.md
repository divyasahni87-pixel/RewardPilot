# RewardPilot RAG Policy Documents v1

Use these files for the policy/exceptions layer of RewardPilot.

- Structured JSON/SQLite: numeric earn rates, transfer ratios, user balances, point valuations.
- RAG: eligibility, exclusions, booking-channel restrictions, transfer mechanics, certificate rules.
- Live API/user input: current cash prices, award prices, availability, Points Boost availability.
- Python: calculations.
- LLM/LangGraph: orchestration and explanation.

For this small corpus, chunk each Markdown document by headings. A practical target is ~400–700 tokens per chunk with modest overlap only when needed.

Every file includes an official source URL and last_verified date. These are curated paraphrases; the official source controls if policy changes.
