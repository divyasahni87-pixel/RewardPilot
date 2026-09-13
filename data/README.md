# RewardPilot Demo Data

This dataset is intentionally small and curated for a Demo Day prototype.

Files:
- card_catalog.json: card earn rules and selected benefits
- transfer_rules.json: supported transferable-points relationships
- redemption_rules.json: deterministic redemption rules safe to calculate with
- demo_scenarios.json: controlled scenarios for testing/demo

Design rules:
1. Official issuer/program sources only.
2. Every rule has a last_verified date.
3. Dynamic prices/award availability are never hard-coded as universal truths.
4. LLM explains; Python calculates.
5. If a dynamic value is missing, the agent must say it cannot compare that path yet.
