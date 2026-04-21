# Architecture (Current Desktop Mode)

## Components

- Desktop UI: `desktop/` (Tauri + React + Vite)
- Local backend: `agent_server.py` (FastAPI, SSE, tool-calling loop)
- RAG: `rag_pipeline/` with local `rag_storage/` and optional Supabase
- Optional LLM providers:
  - llama.cpp server (`LLAMACPP_*`)
  - Ollama (`OLLAMA_*`)
  - OpenAI (`OPENAI_*`)

## Runtime Ports

- `7719`: Agent Server (`agent_server.py`)
- `8080`: llama.cpp server (default)

llama.cpp managed install location:
- packaged app: `<install_dir>/llama.cpp`
- dev mode: `<repo>/tools/llama.cpp`
- `1420`: Vite dev server (desktop frontend during dev)
- `8000`: MCP server (legacy mode)

## Chat Execution Model

`/chat` supports three modes:

- `normal`: tool-calling loop + streamed final response
- `plan`: planning-only response with alternatives and final plan request
- `iterate`: autonomous staged execution with validation and retries

SSE events:
- `run` (run id for trace lookup)
- `step`
- `chunk`
- `confidence`
- `error`
- `done`

Runtime controls:
- `AGENT_MAX_ITERATIONS`
- `AGENT_MAX_TOOL_CALLS`
- `AGENT_MAX_WALL_TIME_SEC`
- `AGENT_TOOL_TIMEOUT_SEC`

## Tool Inventory

- `search_local_knowledge`
- `search_folder_documents`
- `web_search`
- `get_current_time`
- `get_system_stats`
- `list_knowledge_base_files`
- `run_windows_command`
- `verify_file_exists`
- `verify_file_contains`
- `verify_command_output`

Folder-scoped behavior:
- when a conversation has `folder_id`, backend disables `search_local_knowledge` and relies on `search_folder_documents` for exclusive folder docs.

## Folders and Context Isolation

Folders (UI/store level):
- group conversations
- can define:
  - `behaviorId` (base behavior)
  - `customPrompt`
  - `sandboxPath` (project working directory / sandbox root)
- can store folder-exclusive documents under:
  - `data/folders/<folder_id>/...`

Conversation prompt composition:
- conversation behavior prompt
- + folder behavior prompt (if set)
- + folder custom prompt (if set)

## Action Execution Safety

`run_windows_command`:
- blocked patterns for high-risk commands (`format`, `diskpart`, etc.)
- idempotency keys for mutating actions
- dry-run support (`dry_run=true`)
- contract validation + structured retry hints
- execution mode via `AGENT_EXECUTION_MODE`:
  - `confirm`
  - `autonomous`
- `confirm` mode UX:
  - backend emits `command_confirmation_required` step event
  - chat renders action cards (`Ejecutar`, `Rechazar`)
  - approved action executes via `POST /actions/run_windows_command` (explicit user intent)
- sandbox enforcement:
  - if folder has `sandboxPath`, command `cwd` defaults to that sandbox
  - explicit command paths outside sandbox are blocked (`blocked_sandbox`)
  - if no sandbox exists for the folder, backend requires explicit approval before execution
- policy classes via env:
  - `AGENT_POLICY_FILESYSTEM`
  - `AGENT_POLICY_NETWORK`
  - `AGENT_POLICY_PROCESS`
  - `AGENT_POLICY_SYSTEM`
- timeout and output cap:
  - `AGENT_COMMAND_TIMEOUT_SEC`
  - `AGENT_COMMAND_MAX_OUTPUT`

## Memory, Traces, Snapshots

- Long-horizon memory store: `data/memory.jsonl`
  - scoped by `conversation_id` + `folder_id`
  - recency decay + lexical retrieval
- Run traces: `data/runs/<run_id>.json`
  - includes streamed events and mode metadata
- Snapshots: `data/snapshots/<conversation_id>.json`
  - used by iterate mode checkpoints/resume

## Task Router (Area-Based Model Routing)

- Config: `data/.unlz_internal/task_router.json` (legacy `data/task_router.json` auto-migrated)
- Runtime metric log: `data/.unlz_internal/router_metrics.jsonl` (legacy `data/router_metrics.jsonl` auto-migrated)
- Router flow:
  - classify task area from user request
  - pick area winner model (`primary_model`)
  - execute fallback chain (`fallback_models`) on provider/model failure
  - persist success/latency/retry metrics
  - optional periodic recalibration based on observed metrics

Default seeded areas:
- `notificaciones`
- `resumen_asignacion`
- `metadata`
- `jurisdiccion`
- `ocr`
- `rag`
- `chat_general`
- `docgen_informe`
- `vlm`

Desktop Settings support for task router:
- search/filter areas
- create/delete areas from UI
- edit per-area primary/fallback/profile/keywords
- read-only global metrics table with sortable columns and pagination
- local UI persistence for metrics table sort and page size (localStorage)

## Connector Health and Telemetry

- `/connectors/health` surfaces provider/tool latency and error rates.
- Optional telemetry (opt-in):
  - `AGENT_TELEMETRY_OPT_IN=true`
  - writes structured events to `data/telemetry.jsonl`.
- Knowledge Base listing (`GET /files`) only exposes user-document extensions and hides internal files (router/metrics/telemetry).

## Window Controls UX

Configurable in settings / `.env`:
- `WINDOW_CONTROLS_STYLE=windows|mac`
- `WINDOW_CONTROLS_SIDE=left|right`
- `WINDOW_CONTROLS_ORDER=minimize,maximize,close` (any permutation)

## System Telemetry

`/stats` returns:
- CPU, RAM
- VRAM (if available via `nvidia-smi`)
- disk aggregates (backward compatibility)
- per-disk entries (Windows drive letters like `C:`, `D:`)

## UI State Model

Persisted with Zustand:
- conversations
- behaviors
- folders
- active conversation

Chat supports:
- editing user/assistant messages
- recalculation from edited points
- suggestion prefill drafts (initialized once per conversation to avoid draft loss on remount/re-render)

## Legacy Architecture (Compatibility)

- `frontend/` (Next.js) + `mcp_server.py` + optional n8n webhook orchestration
- still present in repo, desktop mode is primary
