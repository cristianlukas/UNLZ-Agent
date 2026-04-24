# ADR 0005: Dev Mode

## Status
Accepted

## Context
Debugging agent failures (wrong tool called, LLM returning bad shapes, task router misconfiguration) required reading raw log files manually. The existing run trace storage (ADR 0001) had no UI. A developer-focused view was needed that didn't clutter the standard UX.

## Decision
Add a `devMode` toggle (off by default) in Settings that unlocks:

**Dev Log view (`/dev` endpoints)**
- `GET /dev/log` — last N lines of `agent_server.log`
- `GET /dev/log/stream` — SSE tail with ~1s polling, emits new lines as they appear
- `GET /dev/traces` — trace summaries: run_id, mode, duration, event count, error count, input preview
- `GET /dev/traces/{run_id}` — full trace with all SSE events
- `DELETE /dev/traces` — bulk delete all trace files

**DevLogView component**
- Two tabs: Server Log (live SSE tail, color-coded by severity) and Trazas (trace card browser with modal detail)
- "Dev Log" nav item in sidebar, amber color, only visible when `devMode=true`

**`devMode` persistence**
- Stored in Zustand `persist` slice → survives app restarts
- Backend endpoints available regardless of `devMode`; flag gates only the UI entry point

## Consequences
- Standard users see no extra UI complexity.
- Developers get full execution visibility without external log tailing.
- Trace files grow unboundedly without manual clearing; `DELETE /dev/traces` provided as manual control.
- SSE log stream polls file every ~1s — minimal overhead, acceptable for debug use.
