# API Reference — agent_server.py

Base URL: `http://127.0.0.1:7719`

All endpoints return JSON unless noted. SSE endpoints return `text/event-stream`.

---

## Root

### `GET /`
```json
{ "status": "online", "service": "UNLZ Agent Server (opencode)", "health": "/health" }
```

---

## Health & Onboarding

### `GET /health`
Returns global status and opencode availability.

```json
{
  "status": "online",
  "components": {
    "llm": {
      "status": "ok",
      "details": "opencode — 0.1.0",
      "state": "ready"
    }
  }
}
```

### `GET /health/onboarding`
Returns onboarding health checks.

```json
{
  "status": "ready",
  "checks": [
    { "id": "provider", "name": "Provider opencode", "status": "ok", "details": "...", "action": "..." },
    { "id": "backend_port", "name": "Backend 7719", "status": "ok", "details": "...", "action": "..." },
    { "id": "mcp_port", "name": "MCP 8000", "status": "warning", "details": "...", "action": "..." },
    { "id": "data_dir", "name": "Escritura en data/", "status": "ok", "details": "...", "action": "..." },
    { "id": "rag_storage", "name": "RAG Chroma", "status": "warning", "details": "...", "action": "..." }
  ],
  "first_prompt_examples": ["...", "...", "..."]
}
```

### `POST /health/onboarding/fix`
Creates required directories and harness dirs.

```json
{ "status": "ok", "message": "Se aplicaron ajustes base de runtime y carpetas." }
```

### `GET /health/center`
Returns comprehensive health status: provider, model alias, opencode version, bootstrap status, recent errors.

---

## Chat

### `POST /chat`
Streaming SSE endpoint. Executes opencode as subprocess with llama.cpp backend.

**Request body:**
```json
{
  "message": "string",
  "history": [{ "role": "user|assistant", "content": "..." }],
  "system_prompt": "optional — behavior system prompt",
  "model_override": "optional — model alias override",
  "harness_override": "optional — always opencode",
  "llamacpp_overrides": {},
  "folder_id": "optional — folder scope",
  "sandbox_root": "optional — absolute path for opencode cwd",
  "mode": "normal",
  "conversation_id": "optional — enables trace persistence",
  "dry_run": false,
  "internet_enabled": true,
  "tools_mode": "auto",
  "user_profile": {
    "experience_level": "newbie",
    "detail_level": "simple",
    "language": "es"
  }
}
```

**SSE event types:**

| type | payload fields | notes |
|------|---------------|-------|
| `run` | `run_id` | first event |
| `timeline` | `stage`, `label`, `ts` | visual stage indicator |
| `step` | `text`, `args` | opencode status, tool calls |
| `chunk` | `text` | streamed LLM output |
| `error` | `text`, `human_message`, `common_causes`, `fix_steps` | explained error |
| `done` | — | stream complete |

**Timeline stages:** `understanding` → `reading` → `planning` → `editing` → `validating` → `generating` → `done`

**User profile injection:**
- `experience_level: newbie/beginner` → "avoid jargon, explain step-by-step"
- `detail_level: simple/short` → "keep explanations simple and actionable"
- `language: es/spanish` → "answer in Spanish"

---

## Run Management

### `POST /runs/{run_id}/cancel`
Cancels an active run by kill PID tree.

```json
{ "status": "cancelling", "run_id": "..." }
```

---

## Settings

### `GET /settings`
Reads `.env` as flat string map.

### `POST /settings`
Writes SCREAMING_SNAKE_CASE keys into `.env` and reloads runtime config.
Blocked keys: `AGENT_HARNESS`, `AGENT_EXECUTION_MODE`, `LLM_PROVIDER`, `LLAMACPP_EXECUTABLE`, `LLAMACPP_MODEL_PATH`, `LLAMACPP_MODEL_ALIAS`.

```json
{ "success": true, "blocked_keys": ["AGENT_HARNESS", ...] }
```

---

## Bootstrap

### `GET /bootstrap/status`
Returns bootstrap state: status (idle/running/downloading/ready/error), detail, model_path, tier, bucket, vram_gb, ram_gb.

---

## Behaviors

### `GET /local/behaviors`
Returns local behaviors from `data/local_behaviors.json`.

---

## Harnesses

### `GET /harnesses/status`
Returns opencode status only.

```json
{
  "active": "opencode",
  "options": [{ "id": "opencode", "label": "opencode", "installed": true, "version": "...", "path": "..." }]
}
```

### `POST /harnesses/install`
Installs opencode via npm.

```json
{ "harness_id": "opencode" }
```

Returns `{ "status": "ok", "path": "...", "version": "..." }`.

---

## System Management

### `POST /system/mcp/start`
Starts MCP server as detached subprocess.

### `POST /system/mcp/stop`
Stops MCP server process.

---

## llama.cpp Management

### `POST /llamacpp/start`
Starts llama.cpp server subprocess with current config.

```json
{ "status": "ready", "detail": "started", "url": "http://127.0.0.1:8081/v1" }
```

### `POST /llamacpp/stop`
Terminates the managed llama.cpp process.

```json
{ "status": "stopped", "url": "http://127.0.0.1:8081/v1" }
```

---

## Opencode Warmup

### `GET /opencode/warmup`
Returns warmup state: status (idle/running/ready/error), detail, started_at, finished_at.

### `POST /opencode/warmup`
Runs opencode warmup. Returns warmup result.

---

## Newbie UX

### `GET /newbie/profile`
Returns user profile: language, experience_level, detail_level.

```json
{ "language": "es", "experience_level": "newbie", "detail_level": "simple" }
```

### `POST /newbie/profile`
Saves/merges user profile.

### `GET /newbie/task-templates`
Returns 4 pre-defined task templates: explain_error, refactor_file, document_module, prepare_pr.

### `POST /newbie/snapshot`
Saves timestamped snapshot to `data/snapshots/`.

---

## Stats

### `GET /stats`
Returns hardware metrics + run statistics.

```json
{
  "cpu_percent": 45.2,
  "ram_total_gb": 32.0,
  "ram_used_gb": 18.4,
  "ram_percent": 57.5,
  "newbie_metrics": {
    "total_runs": 10,
    "successful_runs": 8,
    "failed_runs": 2,
    "success_rate": 80.0,
    "time_to_first_success_sec": 12.5,
    "avg_run_duration_sec": 15.3
  }
}
```

---

## Dev / Debug

### `GET /dev/log?lines=300`
Returns last N lines of `agent_server.log`.

```json
{
  "lines": ["..."],
  "path": "C:\\...\\agent_server.log",
  "exists": true,
  "total": 1840
}
```

### `GET /dev/log/stream?lines=100`
SSE tail of `agent_server.log`. Sends initial lines on connect, then pushes new lines as they appear (~1 s poll).

```json
{ "line": "log line text", "init": true }
```

### `GET /dev/traces?limit=30`
Returns metadata for the most recent run traces (sorted by modification time, newest first).

```json
[{
  "run_id": "a1b2c3d4e5f6",
  "conversation_id": "...",
  "mode": "normal",
  "mode_effective": "opencode",
  "started_at": "2026-05-02T10:00:00",
  "finished_at": "2026-05-02T10:00:05",
  "event_count": 12,
  "error_count": 0,
  "errors": [],
  "input_preview": "Buscar información sobre...",
  "timing": {}
}]
```

### `GET /dev/traces/{run_id}`
Returns the full trace object for one run (all SSE events + metadata).

### `DELETE /dev/traces`
Deletes all trace files under `data/runs/`.

Returns `{ "deleted": N }`.

---

## Tool Execution Notes

**Tool policy in prompt:**
- `tools_mode: without_tools` → "no_tools" in prompt
- `tools_mode: with_tools` → "tools_required" in prompt
- `tools_mode: auto` → "tools_auto" in prompt

**Internet policy in prompt:**
- `internet_enabled: true` → "internet_enabled" in prompt
- `internet_enabled: false` → "internet_disabled" in prompt

**Confusion detection:**
- Detects patterns like "no entend", "explicá más simple", "me perdí"
- Injects: "explain in beginner-friendly steps with plain language and short examples"

**Error explanation:**
- `explain_error_for_humans()` translates technical errors to human-friendly messages
- Returns: `human_message`, `common_causes[]`, `fix_steps[]`
- Special handling for: timeout, missing tools, generic errors
