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

Mode behavior:
- `normal`: standard tool-calling loop
- `plan`: planning only (alternatives + final decision prompt)
- `iterate`: staged autonomous execution + validation + retries
  - supports dependency graph (`depends_on`) + parallelizable stages
  - writes checkpoints/snapshots per `conversation_id`

## Knowledge Base (Global)

### `GET /files`
Lists files under `data/`.

### `POST /upload`
Uploads a file into `data/`.

### `POST /ingest`
Triggers RAG ingestion (`rag_pipeline.ingest.ingest_documents`).

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
- tool execution has typed contract validation + retry hints
- mutating tools support idempotency keys and dry-run
- policy engine (`AGENT_POLICY_FILESYSTEM|NETWORK|PROCESS|SYSTEM=allow|confirm|deny`)
- runtime guardrails: max iterations, max tool calls, wall-time and per-tool timeout
