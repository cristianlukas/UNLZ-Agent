# Next Steps and Roadmap

[🇬🇧 English](Next-Steps.md) | [🇪🇸 Español](Next-Steps_ES.md)

This roadmap focuses on making **UNLZ Agent** structurally stronger as an agent platform (planning, execution, verification, memory, and MCP ecosystem), beyond model quality alone.

## Phase 1: Agent Core (Planning + Execution Loop)

- [x] Add an explicit planner/executor/critic loop in backend (`plan -> execute -> validate -> retry`), not only prompt-level behavior.
- [x] Introduce task graph support (dependent steps, parallelizable steps, checkpoints).
- [x] Add bounded iteration controls: max iterations, max tool calls, max wall-time, and per-step timeout budgets.
- [x] Persist execution traces per run (plan versions, tool calls, outputs, final verdict).

## Phase 2: Tool Reliability and Safety

- [x] Standardize tool contracts: typed input/output schemas, error codes, retry hints.
- [x] Add idempotency keys for mutating tools (`run_windows_command`, file writes) to avoid duplicate side effects.
- [x] Build context-aware policy engine (allow/confirm/deny) by operation class (filesystem/network/process/system).
- [x] Add dry-run mode for actionable tasks before actual execution.

## Phase 3: Verification and Self-Correction

- [x] Add post-action verification primitives (file exists/content changed/command output checks).
- [x] Add automatic fallback strategies when a tool fails (alternative command/query/provider).
- [x] Add confidence scoring per answer and per action.
- [x] Add “unverified claim” detector in research mode and force citations when confidence is low.

## Phase 4: MCP and Integrations

- [x] Split MCP capabilities by domain servers (filesystem, shell, browser, docs, repo) with explicit scopes.
- [x] Add per-server permission profiles and user-visible scope audit.
- [x] Add connector health dashboard (latency, error rate, quota).
- [x] Add pluggable search providers with ranking fusion (Google/DDG/SerpAPI/Bing).

## Phase 5: Memory and Context Engineering

- [x] Add long-horizon memory store with decay + retrieval strategy (recent, semantic, task-linked).
- [x] Add folder-scoped memory and conversation-scoped memory separation.
- [x] Add automatic context compression (summaries + critical facts pinning).
- [x] Add “state snapshots” for resumable multi-session agent tasks.

## Phase 6: Competitive DX (Codex/Claude-class workflow)

- [x] Add first-class “Plan Review” UI: alternatives, tradeoffs, chosen path, explicit approval gate.
- [x] Add “Execution Console” timeline with live step status and replay.
- [x] Add one-click “retry from this step” and “branch from here” controls.
- [x] Add benchmark suite: task success rate, time-to-completion, correction count, token/tool efficiency.

## Phase 7: Production Readiness

- [x] Add CI quality gates: backend tests, frontend tests, packaged smoke tests.
- [x] Add signed release artifacts and reproducible build metadata.
- [x] Add structured telemetry (opt-in) for agent quality metrics.
- [x] Publish architecture decision records (ADR) for key agent/MCP design choices.

