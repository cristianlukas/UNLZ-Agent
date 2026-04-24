# ADR 0003: Harness System

## Status
Accepted

## Context
Different tasks benefit from different LLM prompting strategies and execution layers. Coding tasks need a pragmatic, tool-oriented prompt; general chat needs a neutral one; some users want to delegate execution to external CLIs (claude-code, opencode). A single monolithic system prompt cannot serve all use cases.

## Decision
Introduce a harness abstraction — named execution profiles that control:
- System prompt injection (none / coding-focused / lightweight coder)
- Execution delegation (native FastAPI loop / claude CLI / opencode CLI)

Four harnesses implemented:
- `native` — default; no extra prompt injection; FastAPI tool-calling loop
- `claude-code` — "pragmatic coding agent" system prompt; delegates to `claude` CLI
- `little-coder` — lightweight coder prompt; native execution loop
- `opencode` — delegates to `opencode` CLI

Active harness set via `AGENT_HARNESS` env var or per-request `harness_override`. Install status and version exposed via `GET /harnesses/status`; install/update via `POST /harnesses/install`.

Harness system prompt stacks on top of per-behavior system prompts (behavior → harness → request).

## Consequences
- Users can match execution style to task type without editing system prompts manually.
- External CLI harnesses require those CLIs installed and on PATH.
- Per-request `harness_override` allows single-request overrides without changing global config.
- Adding new harnesses requires only a new profile entry — no structural backend changes.
