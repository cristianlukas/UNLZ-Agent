# Next Steps and Roadmap

[🇬🇧 English](Next-Steps.md) | [🇪🇸 Español](Next-Steps_ES.md)

This roadmap focuses on making **UNLZ Agent** structurally stronger as an agent platform (planning, execution, verification, memory, and MCP ecosystem), beyond model quality alone.

## Phase 1: Agent Core (Planning + Execution Loop)

- [ ] Add an explicit planner/executor/critic loop in backend (`plan -> execute -> validate -> retry`), not only prompt-level behavior.
- [ ] Introduce task graph support (dependent steps, parallelizable steps, checkpoints).
- [ ] Add bounded iteration controls: max iterations, max tool calls, max wall-time, and per-step timeout budgets.
- [ ] Persist execution traces per run (plan versions, tool calls, outputs, final verdict).

## Phase 2: Tool Reliability and Safety

- [ ] Standardize tool contracts: typed input/output schemas, error codes, retry hints.
- [ ] Add idempotency keys for mutating tools (`run_windows_command`, file writes) to avoid duplicate side effects.
- [ ] Build context-aware policy engine (allow/confirm/deny) by operation class (filesystem/network/process/system).
- [ ] Add dry-run mode for actionable tasks before actual execution.

## Phase 3: Verification and Self-Correction

- [ ] Add post-action verification primitives (file exists/content changed/command output checks).
- [ ] Add automatic fallback strategies when a tool fails (alternative command/query/provider).
- [ ] Add confidence scoring per answer and per action.
- [ ] Add “unverified claim” detector in research mode and force citations when confidence is low.

## Phase 4: MCP and Integrations

- [ ] Split MCP capabilities by domain servers (filesystem, shell, browser, docs, repo) with explicit scopes.
- [ ] Add per-server permission profiles and user-visible scope audit.
- [ ] Add connector health dashboard (latency, error rate, quota).
- [ ] Add pluggable search providers with ranking fusion (Google/DDG/SerpAPI/Bing).

## Phase 5: Memory and Context Engineering

- [ ] Add long-horizon memory store with decay + retrieval strategy (recent, semantic, task-linked).
- [ ] Add folder-scoped memory and conversation-scoped memory separation.
- [ ] Add automatic context compression (summaries + critical facts pinning).
- [ ] Add “state snapshots” for resumable multi-session agent tasks.

## Phase 6: Competitive DX (Codex/Claude-class workflow)

- [ ] Add first-class “Plan Review” UI: alternatives, tradeoffs, chosen path, explicit approval gate.
- [ ] Add “Execution Console” timeline with live step status and replay.
- [ ] Add one-click “retry from this step” and “branch from here” controls.
- [ ] Add benchmark suite: task success rate, time-to-completion, correction count, token/tool efficiency.

## Phase 7: Production Readiness

- [ ] Add CI quality gates: backend tests, frontend tests, packaged smoke tests.
- [ ] Add signed release artifacts and reproducible build metadata.
- [ ] Add structured telemetry (opt-in) for agent quality metrics.
- [ ] Publish architecture decision records (ADR) for key agent/MCP design choices.
