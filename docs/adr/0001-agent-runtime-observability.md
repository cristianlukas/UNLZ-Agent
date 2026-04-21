# ADR 0001: Agent Runtime Observability

## Status
Accepted

## Context
UNLZ Agent needed execution transparency and resumability to compete with modern coding agents.

## Decision
- Persist per-run traces under `data/runs/<run_id>.json`.
- Emit `run` SSE events to expose `run_id`.
- Emit `confidence` SSE events per final response.
- Persist snapshots under `data/snapshots/<conversation_id>.json` for iterate mode checkpoints.
- Add opt-in telemetry (`AGENT_TELEMETRY_OPT_IN`) to `data/telemetry.jsonl`.

## Consequences
- Better debugging and replay of agent behavior.
- Safer multi-session task continuation.
- Slight storage growth in `data/`.
