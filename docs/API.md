# API Reference — agent_server.py

Base URL: `http://127.0.0.1:7719`

All endpoints return JSON unless noted. SSE endpoints return `text/event-stream`.

---

## Health & Config

### `GET /health`
Returns global status (`online` | `degraded`) and per-component health.

```json
{
  "status": "online",
  "components": {
    "llm":       { "status": "ok",      "details": "llamacpp — gemma-4-31b" },
    "rag":       { "status": "ok",      "details": "chroma ready" },
    "knowledge": { "status": "warning", "details": "no files ingested" }
  }
}
```

### `GET /settings`
Reads all keys from `.env` as a flat string map.

### `POST /settings`
Writes SCREAMING_SNAKE_CASE keys into `.env` and reloads runtime config.

> **Tauri helpers** (desktop only, invoked via `@tauri-apps/api/core`):
> - `get_settings` — reads `.env` without backend
> - `save_settings` — writes `.env` without backend
> - `pick_directory` — native folder picker dialog
> - `pick_file` — native file picker (used for `llama-server.exe`)
> - `restart_agent` — kills and respawns the Python sidecar
> - `stop_agent` — kills the Python sidecar

---

## Chat

### `POST /chat`
Streaming SSE endpoint. Supports tool-calling loop, planning, and iterative staged execution.

**Request body:**
```json
{
  "message":         "string",
  "history":         [{ "role": "user|assistant", "content": "..." }],
  "system_prompt":   "optional — behavior system prompt override",
  "model_override":  "optional — behavior-level model alias",
  "harness_override":"optional — native|claude-code|little-coder|opencode",
  "llamacpp_overrides": {
    "context_size": 32768,
    "n_gpu_layers": 999,
    "flash_attn": true,
    "cache_type_k": "q8_0",
    "cache_type_v": "q8_0",
    "extra_args": "--jinja --threads 8"
  },
  "folder_id":       "optional — scopes docs and sandbox to folder",
  "sandbox_root":    "optional — absolute path enforced as command cwd",
  "mode":            "normal|plan|iterate|simple",
  "conversation_id": "optional — enables memory retrieval and snapshots",
  "dry_run":         false
}
```

**SSE event types:**

| type | payload fields | notes |
|------|---------------|-------|
| `run` | `run_id` | first event, always present |
| `step` | `text` (tool/event name), `args` | tool invocations, router info |
| `chunk` | `text` | streamed LLM output token |
| `confidence` | `score` (0–1), `tool_calls` | final confidence per response |
| `error` | `text` | non-fatal error |
| `done` | — | stream complete |

**Mode behavior:**

- `normal` — task router classifies request → tool-calling loop → streamed response
- `simple` — skips task router and tool calls, direct LLM answer (fast path)
- `plan` — returns structured alternatives + chosen plan, no execution
- `iterate` — stages: plan → per-stage execution → validation → retry on failure; supports `depends_on` and parallel stages; writes checkpoints via snapshots

**llama.cpp override precedence (runtime):**
- Global baseline comes from `.env` (`LLAMACPP_*`).
- `llamacpp_overrides` in `/chat` overrides only provided fields for that request.
- Missing override fields keep global values.
- If effective model/runtime signature changes, backend restarts managed llama.cpp.

**Task router integration (normal mode):**
- Emits `{"type":"step","text":"task_router","args":{"area":"...","confidence":0.x,...}}`
- When tools fail and a fallback model is used: `{"type":"step","text":"task_router.llm_fallback","args":{...}}`

**Command confirmation flow (confirm mode):**
- Emits `{"type":"step","text":"command_confirmation_required","args":{"command":"...","cwd":"...","idempotency_key":"..."}}`
- UI shows approval cards; user approves via `POST /actions/run_windows_command`

---

## Command Actions

### `POST /actions/run_windows_command`
Executes a user-approved PowerShell/cmd command.

```json
{
  "command":          "New-Item ...",
  "cwd":              "C:\\Users\\...\\project",
  "sandbox_root":     "C:\\Users\\...\\project",
  "timeout_sec":      60,
  "idempotency_key":  "optional dedup key"
}
```

---

## Knowledge Base

### `GET /files`
Lists user-visible KB files under `data/`. Internal artifacts (router config, metrics, telemetry, dot-files) are excluded.

### `POST /upload`
Uploads a file into the global `data/` KB.

### `POST /ingest`
Triggers RAG ingestion pipeline (`rag_pipeline.ingest`).

### `GET /folders/{folder_id}/files`
Lists files scoped to one folder (`data/folders/{folder_id}/`).

### `POST /folders/{folder_id}/upload`
Uploads a file scoped to one folder.

---

## System Stats

### `GET /stats`
Returns hardware metrics.

```json
{
  "cpu_percent":   45.2,
  "ram_total_gb":  32.0,  "ram_used_gb": 18.4,  "ram_percent": 57.5,
  "vram_total_gb": 8.0,   "vram_used_gb": 6.1,  "vram_percent": 76.3,
  "gpus": [{ "name": "RTX 3060", "total_gb": 8.0, "used_gb": 6.1, "percent": 76.3 }],
  "disk_total_gb": 512.0, "disk_used_gb": 200.0, "disk_percent": 39.1,
  "disks": [{ "name": "C:", "mountpoint": "C:\\", "total_gb": 512.0, "used_gb": 200.0, "percent": 39.1 }]
}
```

VRAM fields are absent when no NVIDIA GPU is detected.

---

## Observability

### `GET /connectors/health`
Returns latency/error metrics for web-search providers and each tool.

### `GET /runs/{run_id}`
Returns the full persisted trace for one run (all SSE events + metadata).

### `GET /snapshots`
Lists snapshot metadata for resumable tasks (iterate mode).

### `GET /snapshots/{conversation_id}`
Returns latest checkpoint snapshot for a conversation.

### `POST /snapshots/{conversation_id}`
Saves or overwrites a custom snapshot payload.

---

## Task Router

### `GET /router/config`
Returns current router configuration.

```json
{
  "version": 1,
  "areas": {
    "chat_general": {
      "primary_model":   "gemma-3-4b-it-q4_0",
      "fallback_models": ["qwen3.6-35b-a3b-unsloth-q4_k_m"],
      "profile":         "gemma3_4b_q40_jsonfmt",
      "keywords":        ["hola", "ayuda", "consulta"]
    }
  }
}
```

### `POST /router/config`
Replaces router configuration entirely.

### `GET /router/metrics`
Returns routing quality metrics by area/model: calls, success rate, avg latency ms, avg retries.

### `POST /router/recalibrate`
Recomputes primary/fallback winners from historical metrics for areas with enough samples.

```json
{ "min_samples": 12 }
```

---

## Harnesses

Agent execution mode profiles that change how the LLM is prompted and how responses are post-processed.

### `GET /harnesses/status`
Returns status of all harness options.

```json
{
  "active": "native",
  "options": [
    { "id": "native",       "label": "native",       "installed": true },
    { "id": "claude-code",  "label": "claude-code",  "installed": true,  "version": "1.2.3", "path": "C:\\..." },
    { "id": "little-coder", "label": "little-coder", "installed": false },
    { "id": "opencode",     "label": "opencode",     "installed": false }
  ]
}
```

### `POST /harnesses/install`
Installs or updates a harness.

```json
{ "harness_id": "claude-code" }
```

Returns `{ "status": "ok", "harness_id": "...", "path": "...", "version": "..." }`.

Harness effects:
- `native` — default; no extra prompt injection
- `claude-code` — adds "pragmatic coding agent" prompt; expects `claude` CLI to be installed
- `little-coder` — lightweight coder prompt
- `opencode` — uses opencode CLI as execution layer

---

## llama.cpp Management

### `POST /llamacpp/start`
Starts llama.cpp server subprocess with current config.

### `POST /llamacpp/stop`
Terminates the managed llama.cpp process and kills any orphan listening on the configured port.

### `GET /llamacpp/status`
```json
{
  "running": true,
  "managed": true,
  "pid": 12345,
  "url": "http://127.0.0.1:8080/v1",
  "model": "C:\\...\\model.gguf",
  "alias": "gemma-4-31b"
}
```

### `GET /llamacpp/installer/status`
Returns install state for the managed llama.cpp build.

Fields: `supported` (Windows only), `installed`, `installed_version`, `latest_version`, `update_available`, `executable`.

### `POST /llamacpp/installer/run`
Downloads latest compatible Windows release from GitHub, extracts to:
- packaged app: `<install_dir>/llama.cpp`
- dev mode: `<repo>/tools/llama.cpp`

Auto-configures `LLAMACPP_EXECUTABLE`, `LLAMACPP_MODELS_DIR` and related `.env` values.

### `GET /models/gguf`
Scans `LLAMACPP_MODELS_DIR` and related paths for `.gguf` files. Returns array of:

```json
{
  "path":    "C:\\...\\model.gguf",
  "name":    "model.gguf",
  "stem":    "model",
  "alias":   "model",
  "size_gb": 4.4,
  "folder":  "models"
}
```

---

## Model Hub

Downloads and manages GGUF models from HuggingFace with hardware-aware recommendations.

### `GET /hub/catalog`
Returns curated model catalog + hardware-based recommendations.

```json
{
  "hardware": { "vram_gb": 8.0, "ram_gb": 32.0, "tier": "mid" },
  "catalog":  [ ...HubModel... ],
  "recommendations": {
    "tier":        "mid",
    "ideal":       { ...HubModel... },
    "balanced":    { ...HubModel... },
    "fast":        { ...HubModel... },
    "all_fitting": [ ...HubModel... ]
  }
}
```

**Hardware tiers:** `entry` (<4 GB VRAM), `mid` (4–8 GB), `high` (8–16 GB), `ultra` (16+ GB).  
CPU-only fallback uses RAM thresholds.

**HubModel fields:** `id`, `family`, `name`, `version`, `size_label`, `hf_repo`, `filename`, `quant`, `vram_gb`, `ram_gb`, `file_gb`, `context`, `tier`, `tasks` (chat/code/reasoning/instruct 0–100), `license`, `release`, `recommended_for`, `badge`.

### `GET /hub/check-update`
Compares the current loaded model against the catalog and returns upgrade suggestions.

```json
{
  "update": {
    "type":           "family_upgrade|same_family_upgrade|catalog_suggestion",
    "current_family": "gemma3",
    "new_family":     "qwen3",
    "recommended":    { ...HubModel... },
    "message":        "Nueva familia disponible: Qwen3 8B"
  },
  "current_model": "C:\\...\\model.gguf"
}
```

Returns `{ "update": null }` when no upgrade is detected.

### `POST /hub/download`
Starts a background download from HuggingFace. Returns `{ "download_id": "abc12345" }`.

```json
{
  "hf_repo":  "bartowski/Qwen3-8B-GGUF",
  "filename": "Qwen3-8B-Q4_K_M.gguf",
  "dest_dir": "C:\\...\\models"   // optional, defaults to LLAMACPP_MODELS_DIR
}
```

### `GET /hub/download/{download_id}`
SSE progress stream for an active download.

```json
{
  "status":        "starting|downloading|done|error|cancelled",
  "progress":      0.0–1.0,
  "downloaded_gb": 2.1,
  "total_gb":      5.2,
  "speed_mbps":    18.4,
  "eta_s":         180,
  "error":         null,
  "filename":      "Qwen3-8B-Q4_K_M.gguf",
  "dest_path":     "C:\\...\\Qwen3-8B-Q4_K_M.gguf"
}
```

### `DELETE /hub/download/{download_id}`
Cancels an active download and removes the partial file.

### `POST /hub/apply/{download_id}`
Applies a completed download: writes `LLAMACPP_MODEL_PATH` + `LLAMACPP_MODEL_ALIAS` to `.env` and restarts llama.cpp.

Returns `{ "status": "applied", "model_path": "...", "alias": "...", "warning": null }`.

### `GET /hub/downloads`
Returns all known downloads (active + history) for the current session.

---

## Dev / Debug

Available when backend is running. The desktop Dev Log view uses these endpoints.

### `GET /dev/log?lines=300`
Returns last N lines of `agent_server.log`.

```json
{
  "lines":  ["UNLZ Agent Server v2 ...", "Provider: llamacpp", ...],
  "path":   "C:\\...\\agent_server.log",
  "exists": true,
  "total":  1840
}
```

### `GET /dev/log/stream?lines=100`
SSE tail of `agent_server.log`. Sends initial `lines` on connect, then pushes new lines as they appear (~1 s poll).

```json
{ "line": "log line text", "init": true }
```

### `GET /dev/traces?limit=30`
Returns metadata for the most recent run traces (sorted by modification time, newest first).

```json
[{
  "run_id":          "a1b2c3d4e5f6",
  "conversation_id": "...",
  "mode":            "normal",
  "started_at":      "2025-04-22T10:00:00",
  "finished_at":     "2025-04-22T10:00:05",
  "event_count":     12,
  "error_count":     0,
  "errors":          [],
  "input_preview":   "Buscar información sobre..."
}]
```

### `GET /dev/traces/{run_id}`
Returns the full trace object for one run (identical to `GET /runs/{run_id}`).

### `DELETE /dev/traces`
Deletes all trace files under `data/runs/`.

Returns `{ "deleted": N }`.

---

## Tool Execution Notes

**Tool catalog:**

| tool | purpose |
|------|---------|
| `search_local_knowledge` | semantic search over global RAG KB |
| `search_folder_documents` | semantic search over folder-scoped docs |
| `web_search` | live web search (Google / DuckDuckGo / SerpAPI / Bing / fusion / auto) |
| `get_current_time` | returns current timestamp |
| `get_system_stats` | CPU, RAM, VRAM, disk |
| `list_knowledge_base_files` | list files in KB |
| `run_windows_command` | executes a PowerShell/cmd command with sandbox + policy enforcement |
| `verify_file_exists` | used by iterate mode validation |
| `verify_file_contains` | used by iterate mode validation |
| `verify_command_output` | used by iterate mode validation |

**Routing heuristics:**
- Research prompts → tool call forced on iteration 0
- Action prompts → `run_windows_command` prioritized
- Greetings/smalltalk → tool calls skipped entirely (no `tools` param sent to LLM)
- Folder-scoped chat → `search_local_knowledge` excluded, folder docs preferred

**Execution safety:**
- `AGENT_EXECUTION_MODE=confirm|autonomous`
- Policy engine: `AGENT_POLICY_FILESYSTEM|NETWORK|PROCESS|SYSTEM=allow|confirm|deny`
- Sandbox enforcement via `sandbox_root`
- Blocked commands (hardcoded): `format`, `diskpart`, `del /f /s /q C:\`, etc.
- Idempotency keys + `dry_run=true` support for mutating tools
- Runtime guards: `AGENT_MAX_ITERATIONS`, `AGENT_MAX_TOOL_CALLS`, `AGENT_MAX_WALL_TIME_SEC`, `AGENT_TOOL_TIMEOUT_SEC`

**LLM fallback behavior:**
- `_chat_create_with_fallback` tries each model in the task-router model chain.
- If a response has no `.choices` (common with tool-calling on models without function-call support), automatically retries the same model without `tools`/`tool_choice` before moving to the next model in chain.
- `tool_choice="required"` is never used (breaks many llama.cpp builds); always `"auto"`.
