# Next Steps and Roadmap

[🇬🇧 English](Next-Steps.md) | [🇪🇸 Español](Next-Steps_ES.md)

Roadmap updated for the current project state (desktop + agent_server).

## Phase 1: Operational Stability

- [ ] Add automated tests for `/chat` (`step/chunk/error/done` paths).
- [ ] Add tests for `web_search` fallback (no results and provider errors).
- [ ] Add baseline metrics (latency, endpoint errors, tool failures).
- [ ] Implement `agent_server.log` rotation.

## Phase 2: Agent and Tools

- [ ] Improve Windows command policy (context-aware allowlists + audit trail).
- [ ] Add granular confirmations by operation type (filesystem, network, processes).
- [ ] Add source/citation handling for research responses using `web_search`.
- [ ] Add additional configurable web-search backend (e.g., SerpAPI/Bing).

## Phase 3: Chat UX

- [ ] Show tool-failure reason with expandable technical details in UI.
- [ ] Add message edit history (lightweight versioning).
- [ ] Accessibility improvements (focus states, shortcuts, screen reader support).

## Phase 4: Distribution

- [ ] CI pipeline for portable builds (`build-portable.ps1`) with versioned artifacts.
- [ ] Binary signing for Windows distribution.
- [ ] Reproducible release guide (checklist + semantic versioning).

## Phase 5: Documentation

- [ ] Keep API docs synchronized by version.
- [ ] Add a dedicated "breaking changes" section between legacy and desktop modes.
- [ ] Publish sequence diagrams for chat + tools + SSE flow.
