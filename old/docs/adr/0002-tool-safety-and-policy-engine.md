# ADR 0002: Tool Safety and Policy Engine

## Status
Accepted

## Context
The agent executes local machine actions and requires deterministic, auditable safeguards.

## Decision
- Enforce typed tool contracts with required arguments and retry hints.
- Support idempotency keys for mutating commands.
- Add dry-run mode for action previews (`dry_run=true`).
- Apply operation-class policies via env:
  - `AGENT_POLICY_FILESYSTEM`
  - `AGENT_POLICY_NETWORK`
  - `AGENT_POLICY_PROCESS`
  - `AGENT_POLICY_SYSTEM`
  with values `allow|confirm|deny`.

## Consequences
- Lower risk for unintended actions.
- Better retry ergonomics and clearer failure reasons.
- More predictable execution behavior across sessions.
