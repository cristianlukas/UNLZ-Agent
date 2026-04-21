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
- `step`
- `chunk`
- `error`
- `done`

## Tool Inventory

- `search_local_knowledge`
- `search_folder_documents`
- `web_search`
- `get_current_time`
- `get_system_stats`
- `list_knowledge_base_files`
- `run_windows_command`

Folder-scoped behavior:
- when a conversation has `folder_id`, backend disables `search_local_knowledge` and relies on `search_folder_documents` for exclusive folder docs.

## Folders and Context Isolation

Folders (UI/store level):
- group conversations
- can define:
  - `behaviorId` (base behavior)
  - `customPrompt`
- can store folder-exclusive documents under:
  - `data/folders/<folder_id>/...`

Conversation prompt composition:
- conversation behavior prompt
- + folder behavior prompt (if set)
- + folder custom prompt (if set)

## Action Execution Safety

`run_windows_command`:
- blocked patterns for high-risk commands (`format`, `diskpart`, etc.)
- execution mode via `AGENT_EXECUTION_MODE`:
  - `confirm`
  - `autonomous`
- timeout and output cap:
  - `AGENT_COMMAND_TIMEOUT_SEC`
  - `AGENT_COMMAND_MAX_OUTPUT`

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
