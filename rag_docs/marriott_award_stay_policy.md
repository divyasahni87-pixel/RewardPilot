---
title: "Marriott Bonvoy — Award Redemption Stay Rules"
program: "Marriott Bonvoy"
tags: ["marriott","bonvoy","award stay","redeem points","hotel"]
source_url: "https://www.marriott.com/loyalty/terms/default.mi"
last_verified: "2026-09-12"
document_type: "curated_policy_summary"
policy_type: "redemption_policy"
---
# Marriott Bonvoy — Award Redemption Stay Rules

## Award redemption stays
Marriott Bonvoy members can redeem points for eligible stays at participating properties.

## Key conditions
- Award stays are subject to availability at reservation time.
- The points required are dynamic and must come from the current Marriott booking flow or user-provided award price.
- Marriott can change award levels, availability, participating properties, and program rules.

## RewardPilot rule
Never store a hotel's required points price as a permanent RAG fact. For example, “Hotel X costs 45,000 points” is current booking data, not policy.

## How RewardPilot should use this
RAG establishes whether and how Marriott points can be used. Live search/API or user input supplies the current points price.
