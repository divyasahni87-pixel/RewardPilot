# RewardPilot

Launch from the project root:

```powershell
uv run streamlit run app.py
```

Open http://localhost:8501. The server binds to the local computer.

The interface reads existing wallet user 1 without creating or modifying wallet
records. Configure the existing `NEBIUS_API_KEY`, `PINECONE_API_KEY`, and optional
`PINECONE_INDEX` environment variables as before. Credentials are never shown in
the interface. No remote analysis runs until **Find My Best Option** is selected.

`ui_agent.py` invokes the existing agent, captures completed tool messages, and
returns structured cash results, award results, retrieved evidence, completed
activity labels, and the final public answer. Intermediate model content and
reasoning metadata are never sent to the UI. Unexpected tool inputs cannot be
displayed as if they matched the submitted booking.

Booking channels map to `direct`, `amex_travel`, `chase_travel`, and an empty
string for an unknown channel. Existing purchase-mapper behavior is preserved,
including its current category coverage. A missing channel is not silently
treated as direct. Discount status is sent as context; the entered award price
is never changed by the interface.

Offline checks:

```powershell
uv run python -m unittest test_app test_agent_components test_ingest_pinecone test_wallet_db
uv run python test_decision_engine.py
```

Live integration checks (send wallet/scenario data to the configured existing
Nebius/Pinecone workflow):

```powershell
uv run python test_ui_agent_live.py
```

The live check writes a local, gitignored `ui_live_results.json`. UI results are
session-local and remain visible across widget changes, with a notice when they
refer to the previous submitted inputs. Failed analyses retain the previous
successful result and show a friendly message.
