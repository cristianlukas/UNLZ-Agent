# API Reference (agent_server.py)

Base URL: `http://127.0.0.1:7719`

## Health and Config

### `GET /health`
Returns component status (`llm`, `rag`, `knowledge`) and global state (`online` or `degraded`).

### `GET /settings`
Reads `.env` key/value pairs.

### `POST /settings`
Persists uppercase config keys into `.env` and reloads env values.

Desktop (Tauri) helpers used by Settings UI:
- `pick_directory` (native folder picker)
- `pick_file` (native file picker, used for `llama-server.exe`)

## Chat

### `POST /chat`
Streaming SSE endpoint.

Request body:

```json
{
  "message": "string",
  "history": [{ "role": "user|assistant", "content": "..." }],
  "system_prompt": "optional behavior prompt",
  "folder_id": "optional folder scope id",
  "sandbox_root": "optional folder sandbox root path",
  "mode": "normal|plan|iterate",
  "conversation_id": "optional stable id for memory/snapshots",
  "dry_run": false
}
```

SSE event payloads (`data: {...}`):

- `{"type":"run","run_id":"..."}`
- `{"type":"step","text":"tool_name","args":{...}}`
- `{"type":"chunk","text":"partial assistant output"}`
- `{"type":"confidence","score":0.0-1.0,"tool_calls":N}`
- `{"type":"error","text":"error message"}`
- `{"type":"done"}`

When a command requires confirmation in `AGENT_EXECUTION_MODE=confirm`, chat stream emits:
- `{"type":"step","text":"command_confirmation_required","args":{"command":"...","cwd":"...","idempotency_key":"..."}}`

Sandbox behavior for `run_windows_command`:
- if `sandbox_root` is configured for the folder, command execution is constrained to that directory
- explicit paths outside sandbox are blocked (`blocked_sandbox`)
- if no sandbox is configured, backend asks explicit confirmation before execution (`needs_confirmation`)

Mode behavior:
- `normal`: standard tool-calling loop
- `plan`: planning only (alternatives + final decision prompt)
- `iterate`: staged autonomous execution + validation + retries
  - supports dependency graph (`depends_on`) + parallelizable stages
  - writes checkpoints/snapshots per `conversation_id`

## Knowledge Base (Global)

### `GET /files`
Lists user-facing Knowledge Base files under `data/`.
Internal runtime artifacts are excluded (for example `task_router.json`, `router_metrics.jsonl`, telemetry logs, and hidden dot-files).

### `POST /upload`
Uploads a file into `data/`.

### `POST /ingest`
Triggers RAG ingestion (`rag_pipeline.ingest.ingest_documents`).

## Command Approval Actions

### `POST /actions/run_windows_command`
Executes a previously proposed command as an explicit user-approved action (used by confirmation cards in UI).

Request body:
```json
{
  "command": "New-Item ...",
  "cwd": "C:\\Users\\...",
  "sandbox_root": "C:\\Users\\...\\project",
  "timeout_sec": 60,
  "idempotency_key": "optional"
}
```

## Folder-Scoped Documents

### `GET /folders/{folder_id}/files`
Lists files attached to one folder (`data/folders/{folder_id}`).

### `POST /folders/{folder_id}/upload`
Uploads a file attached only to that folder context.

## System Stats

### `GET /stats`
Returns:
- `cpu_percent`
- `ram_total_gb`, `ram_used_gb`, `ram_percent`
- `vram_total_gb`, `vram_used_gb`, `vram_percent`, `gpus[]`
- aggregate disk fields: `disk_total_gb`, `disk_used_gb`, `disk_percent`
- per-disk array: `disks[]`

## Agent Runtime Observability

### `GET /runs/{run_id}`
Returns full persisted trace for one run (events, mode, metadata).

### `GET /connectors/health`
Returns aggregated connector metrics:
- web-search providers (latency/error rates)
- tool runtime metrics (latency/error rates)

### `GET /router/config`
Returns current task-router configuration (`areas`, winner model, fallbacks, keywords, profile).

### `POST /router/config`
Replaces task-router configuration.

### `GET /router/metrics`
Returns live summary of routing quality by area/model:
- calls
- success rate
- avg latency
- avg retries

### `POST /router/recalibrate`
Recomputes winners from historical metrics and updates primary/fallback models when enough samples exist.

### `GET /snapshots`
Lists snapshot metadata for resumable multi-session tasks.

### `GET /snapshots/{conversation_id}`
Returns latest saved snapshot for a conversation.

### `POST /snapshots/{conversation_id}`
Saves/overwrites a custom snapshot payload.

## llama.cpp Management

### `POST /llamacpp/start`
Starts llama.cpp server with configured model and args.

### `POST /llamacpp/stop`
Stops managed llama.cpp process.

### `GET /llamacpp/status`
Returns process state, PID (if managed), URL and model info.

### `GET /llamacpp/installer/status`
Returns install/update state for llama.cpp:
- `installed`, `installed_version`
- `latest_version`, `update_available`
- detected executable path and support status

### `POST /llamacpp/installer/run`
Downloads latest compatible Windows llama.cpp release, extracts it under:
- packaged app: `<install_dir>/llama.cpp`
- dev mode: `<repo>/tools/llama.cpp`

Then it auto-configures `.env` (`LLAMACPP_EXECUTABLE`, `LLAMACPP_MODELS_DIR`, provider and baseline defaults).

### `GET /models/gguf`
Scans known roots for `.gguf` models and returns metadata.

Usage in desktop UI:
- powers the model dropdown in Settings
- supports live rescan (`↻`) without restarting the app

## Tool Execution Notes

Tool catalog used by the agent:
- `search_local_knowledge`
- `search_folder_documents`
- `web_search`
- `get_current_time`
- `get_system_stats`
- `list_knowledge_base_files`
- `run_windows_command`

Notable behavior:
- research-like prompts can force at least one tool attempt first
- action-like prompts can force tool usage and prefer `run_windows_command`
- when web search is unavailable, backend emits explicit failure text
- in folder-scoped chat, `search_local_knowledge` is excluded and folder docs are preferred
- Windows command execution mode is controlled by `AGENT_EXECUTION_MODE`
- In `confirm` mode, UI shows approval cards (`Ejecutar` / `Rechazar`) from `command_confirmation_required` events
- Folder sandbox is enforced when provided (`sandbox_root`); commands outside it are blocked
- tool execution has typed contract validation + retry hints
- mutating tools support idempotency keys and dry-run
- policy engine (`AGENT_POLICY_FILESYSTEM|NETWORK|PROCESS|SYSTEM=allow|confirm|deny`)
- runtime guardrails: max iterations, max tool calls, wall-time and per-tool timeout
- task router:
  - automatic area classification (keywords/intention)
  - model routing by area
  - fallback model chain per request
  - metric logging + recalibration loop
