# Architecture (Current Desktop Mode)

## High-Level Overview

```
┌─────────────────────────────────────────────────────────┐
│  Tauri v2 Desktop App  (desktop/)                       │
│  React + Vite + Zustand                                 │
│  ┌───────────────┐  ┌───────────────────────────────┐   │
│  │ ConvSidebar   │  │ Views: Chat / Behaviors /     │   │
│  │ (nav + convs) │  │ Knowledge / Folders / System /│   │
│  └───────────────┘  │ Settings / ModelHub / DevLog  │   │
│                     └───────────────────────────────┘   │
└───────────────────────────┬─────────────────────────────┘
                            │ HTTP + SSE  (port 7719)
                            ▼
┌─────────────────────────────────────────────────────────┐
│  agent_server.py  (FastAPI)                             │
│  ├─ /chat  (SSE tool-calling loop, modes, harnesses)    │
│  ├─ /actions  (command execution + policy engine)       │
│  ├─ /hub  (model catalog + HF downloads)                │
│  ├─ /llamacpp  (process lifecycle + installer)          │
│  ├─ /router  (area-based model routing)                 │
│  ├─ /harnesses  (execution mode profiles)               │
│  ├─ /dev  (log tail + run traces — dev mode)            │
│  └─ /knowledge, /folders, /stats, /health, /settings   │
└──────────┬──────────────────────────────────────────────┘
           │ OpenAI-compat REST  (port 8080)
           ▼
┌──────────────────────┐   or   ┌──────────┐  ┌──────────┐
│  llama.cpp server    │        │  Ollama  │  │  OpenAI  │
│  (managed subprocess)│        └──────────┘  └──────────┘
└──────────────────────┘
```

---

## Components

- **Desktop UI**: `desktop/` — Tauri v2 + React + Vite + Tailwind + Zustand
- **Local backend**: `agent_server.py` — FastAPI, SSE streaming, tool-calling loop
- **RAG**: `rag_pipeline/` — local ChromaDB in `rag_storage/` + optional Supabase
- **Model catalog**: `hub_catalog.py` — hardware profiler + curated GGUF catalog
- **LLM providers** (pluggable):
  - llama.cpp server (`LLAMACPP_*` env vars) — primary, managed subprocess
  - Ollama (`OLLAMA_*`)
  - OpenAI (`OPENAI_*`)

---

## Runtime Ports

| Port | Service |
|------|---------|
| `7719` | Agent Server (`agent_server.py`) |
| `8080` | llama.cpp server (configurable) |
| `1420` | Vite dev server (desktop frontend, dev only) |
| `8000` | MCP server (legacy mode) |

llama.cpp managed install location:
- packaged app: `<install_dir>/llama.cpp`
- dev mode: `<repo>/tools/llama.cpp`

---

## Chat Execution Model

`POST /chat` is the primary SSE endpoint. Supports four modes:

| mode | behavior |
|------|---------|
| `normal` | task router → tool-calling loop → streamed response |
| `simple` | skip task router + tool calls, direct LLM answer (fast path) |
| `plan` | returns structured alternatives + chosen plan, no execution |
| `iterate` | plan → per-stage execution → validation → retry; supports `depends_on` + parallel stages; writes checkpoints |

**SSE event types:**

| type | payload | notes |
|------|---------|-------|
| `run` | `run_id` | first event, always |
| `step` | `text`, `args` | tool calls, router info, command confirmations |
| `chunk` | `text` | streamed LLM token |
| `confidence` | `score`, `tool_calls` | final per-response quality signal |
| `error` | `text` | non-fatal error |
| `done` | — | stream complete |

**Task router integration (normal mode):**
- Classifies request area → picks primary model → falls back through chain on failure
- Emits `step` events for `task_router` and `task_router.llm_fallback`

**LLM fallback behavior (`_chat_create_with_fallback`):**
- Iterates model chain in order
- If response lacks `.choices` (model doesn't support tool calling), automatically retries same model without `tools`/`tool_choice` before advancing chain
- `tool_choice="required"` never used — breaks many llama.cpp builds; always `"auto"`
- Empty `available_tools` list → no `tools` param sent to LLM at all

**Runtime controls:**
- `AGENT_MAX_ITERATIONS`
- `AGENT_MAX_TOOL_CALLS`
- `AGENT_MAX_WALL_TIME_SEC`
- `AGENT_TOOL_TIMEOUT_SEC`

---

## Harness System

Harnesses are execution mode profiles that change how the LLM is prompted and how responses are post-processed.

| harness | behavior |
|---------|---------|
| `native` | default; no extra prompt injection |
| `claude-code` | adds "pragmatic coding agent" system prompt; delegates to `claude` CLI |
| `little-coder` | lightweight coder prompt injection |
| `opencode` | uses `opencode` CLI as execution layer |

- Active harness set via `POST /settings` (`AGENT_HARNESS`) or overridden per-request (`harness_override`)
- Install status exposed via `GET /harnesses/status`; install/update via `POST /harnesses/install`
- Harness profiles stack on top of behavior-level system prompts

---

## Behavior-Level llama.cpp Overrides

Behaviors can optionally define per-profile llama.cpp runtime overrides:

- `context_size`
- `n_gpu_layers`
- `flash_attn`
- `cache_type_k`
- `cache_type_v`
- `extra_args`

Flow:

1. User selects behavior in chat.
2. Frontend sends `llamacpp_overrides` in `POST /chat`.
3. Backend merges runtime config with precedence:
   - global `.env` (`LLAMACPP_*`) as baseline
   - behavior override as final value (only for provided fields)
4. If effective runtime signature changes (model and/or runtime args), backend restarts managed llama.cpp with merged args.
5. If next conversation/behavior has no override, runtime reverts to global baseline.

---

## Tool Inventory

| tool | purpose |
|------|---------|
| `search_local_knowledge` | semantic search over global RAG KB |
| `search_folder_documents` | semantic search over folder-scoped docs |
| `web_search` | live web search (Google/DuckDuckGo/SerpAPI/Bing/fusion/auto) |
| `get_current_time` | current timestamp |
| `get_system_stats` | CPU, RAM, VRAM, disk |
| `list_knowledge_base_files` | list files in KB |
| `run_windows_command` | PowerShell/cmd with sandbox + policy enforcement |
| `verify_file_exists` | iterate mode validation |
| `verify_file_contains` | iterate mode validation |
| `verify_command_output` | iterate mode validation |

**Routing heuristics:**
- Research prompts → tool call forced on iteration 0
- Action prompts → `run_windows_command` prioritized
- Greetings/smalltalk → tool calls skipped entirely
- Folder-scoped chat → `search_local_knowledge` excluded, folder docs preferred

---

## Action Execution Safety

`run_windows_command` enforcement layers:

1. **Blocked patterns** — hardcoded deny list (`format`, `diskpart`, `del /f /s /q C:\`, etc.)
2. **Policy engine** — per-class allow/confirm/deny via env vars:
   - `AGENT_POLICY_FILESYSTEM`
   - `AGENT_POLICY_NETWORK`
   - `AGENT_POLICY_PROCESS`
   - `AGENT_POLICY_SYSTEM`
3. **Execution mode** (`AGENT_EXECUTION_MODE`):
   - `confirm` → backend emits `command_confirmation_required` step; UI shows approval cards; user approves via `POST /actions/run_windows_command`
   - `autonomous` → executes directly
4. **Sandbox enforcement** — `sandbox_root` restricts command `cwd`; paths outside sandbox blocked
5. **Idempotency keys** + `dry_run=true` support for mutating tools
6. **Timeouts/output caps**: `AGENT_COMMAND_TIMEOUT_SEC`, `AGENT_COMMAND_MAX_OUTPUT`

---

## Folders and Context Isolation

Folders group conversations and define execution context:
- `behaviorId` — base behavior for all conversations in folder
- `customPrompt` — additional prompt injected
- `sandboxPath` — project working directory / sandbox root
- Folder-exclusive documents: `data/folders/<folder_id>/`

Conversation prompt composition (in order):
1. Conversation behavior prompt
2. + Folder behavior prompt (if set)
3. + Folder custom prompt (if set)

When `folder_id` set on `/chat`:
- `search_local_knowledge` disabled
- `search_folder_documents` used exclusively
- Backend scopes docs/sandbox to folder

---

## Memory, Traces, Snapshots

| artifact | location | purpose |
|---------|---------|---------|
| Memory | `data/memory.jsonl` | long-horizon memory; scoped by `conversation_id` + `folder_id`; recency decay + lexical retrieval |
| Run traces | `data/runs/<run_id>.json` | all SSE events + metadata per run; exposed via `/dev/traces` and `/runs/{run_id}` |
| Snapshots | `data/snapshots/<conversation_id>.json` | iterate mode checkpoints; resumable multi-session tasks |
| Telemetry | `data/telemetry.jsonl` | opt-in structured events (`AGENT_TELEMETRY_OPT_IN=true`) |

---

## Task Router (Area-Based Model Routing)

- Config: `data/.unlz_internal/task_router.json`
- Metrics log: `data/.unlz_internal/router_metrics.jsonl`
- Flow: classify area → pick `primary_model` → fallback chain on failure → persist success/latency/retry metrics
- Optional recalibration: `POST /router/recalibrate` recomputes winners from historical metrics

Default seeded areas: `notificaciones`, `resumen_asignacion`, `metadata`, `jurisdiccion`, `ocr`, `rag`, `chat_general`, `docgen_informe`, `vlm`

Desktop Settings UI:
- Search/filter/create/delete areas
- Edit per-area primary/fallback/profile/keywords
- Read-only global metrics table with sort + pagination

---

## Model Hub

Hardware-aware model catalog with 1-click HuggingFace downloads.

### Hardware Profiler (`hub_catalog.py`)

`classify_hardware(vram_gb, ram_gb)` → tier:

| tier | VRAM | RAM fallback |
|------|------|-------------|
| `entry` | < 4 GB | < 8 GB |
| `mid` | 4–8 GB | 8–16 GB |
| `high` | 8–16 GB | 16–32 GB |
| `ultra` | 16+ GB | 32+ GB |

### Catalog

Curated GGUF models from HuggingFace: Qwen3, Gemma3, Llama 3.2, Mistral, DeepSeek-R1. Each model has task scores (chat/code/reasoning/instruct 0–100), hardware requirements, and tier tag.

`get_recommendations(vram_gb, ram_gb)` → `{tier, ideal, balanced, fast, all_fitting}`

### Update Detection

`check_for_update(current_path, current_alias)` detects:
- Same-family upgrade (e.g. newer quant or version)
- Cross-family upgrade (e.g. Gemma3 → Qwen3)

Uses `FAMILY_DETECT` dict (sorted by specificity) + `FAMILY_UPGRADES` mapping.

### Download Pipeline

`POST /hub/download` → starts background thread using `urllib.request` chunked reads. No extra dependencies.
- Downloads to `<dest>.part`, atomic rename on completion
- Tracks: progress, speed (Mbps), ETA, status
- SSE progress stream: `GET /hub/download/{id}`
- Cancel: `DELETE /hub/download/{id}` (removes partial file)
- Apply: `POST /hub/apply/{id}` — writes `LLAMACPP_MODEL_PATH` + `LLAMACPP_MODEL_ALIAS` to `.env`, restarts llama.cpp

### UI

- Hardware banner with tier badge
- Update notification banner (skip/snooze/apply actions) — persisted in Zustand store
- Tabs: Recomendados | Catálogo | Descargando
- Model cards with task score bars, expand for details
- Amber dot badge on "Modelos" sidebar nav when update available

---

## Dev Mode

Developer tooling for tracing and log inspection. Gated behind `devMode` toggle in Settings.

### Trace Storage

Every `/chat` run writes `data/runs/<run_id>.json` with:
- All SSE events (type, text, args, timestamps)
- Input (message, mode, conversation_id)
- Started/finished timestamps
- Error list

### Dev Log Endpoints

| endpoint | purpose |
|---------|---------|
| `GET /dev/log?lines=N` | last N lines of `agent_server.log` |
| `GET /dev/log/stream` | SSE tail — polls file every ~1s, emits new lines |
| `GET /dev/traces?limit=N` | trace summaries (run_id, mode, duration, error count, input preview) |
| `GET /dev/traces/{run_id}` | full trace for one run |
| `DELETE /dev/traces` | delete all trace files |

### Dev Log UI (`DevLogView`)

Two tabs:
- **Server Log** — live SSE tail with color-coded lines (errors red, warnings amber, `[UNLZ]` prefix accent). Live checkbox + manual refresh.
- **Trazas** — trace card list with error badge, duration, input preview; click to open modal with all SSE events.

Dev Log nav item (amber color) only visible when `devMode=true`.

---

## Connector Health and Telemetry

- `GET /connectors/health` — provider/tool latency and error rates
- Opt-in telemetry: `AGENT_TELEMETRY_OPT_IN=true` → `data/telemetry.jsonl`
- `GET /files` hides internal files (router config, metrics, telemetry, dot-files)

---

## UI State Model

Zustand store (`desktop/src/lib/store.ts`), persisted to localStorage:

| key | type | persisted | purpose |
|-----|------|-----------|---------|
| `conversations` | `Conversation[]` | ✓ | all conversations |
| `behaviors` | `Behavior[]` | ✓ | behavior profiles |
| `folders` | `Folder[]` | ✓ | folder groups |
| `activeConvId` | `string\|null` | ✓ | active conversation |
| `view` | `View` | — | current main panel |
| `agentReady` | `boolean` | — | backend health poll |
| `llmReady` | `boolean` | — | LLM component status |
| `providerInfo` | object | — | provider name + model |
| `devMode` | `boolean` | ✓ | show Dev Log + traces |
| `hubUpdateNotification` | `HubUpdateNotification\|null` | — | pending model upgrade |
| `skippedHubModelIds` | `string[]` | ✓ | user-skipped hub models |
| `snoozedHubUntil` | `number\|null` | ✓ | snooze timestamp |

`View` type: `"chat" | "behaviors" | "knowledge" | "folders" | "system" | "settings" | "hub" | "devlog"`

Chat-level features:
- Message editing (user + assistant) with recalculation from edit point
- Suggestion prefill drafts (initialized once per conversation)

---

## Desktop Component Map

| component | view | purpose |
|-----------|------|---------|
| `TitleBar` | always | window controls, health indicator, provider info |
| `ConversationSidebar` | always | conversation list, folder groups, bottom nav |
| `ChatView` | chat | message thread, input, tool step display, command approval cards |
| `BehaviorsView` | behaviors | behavior CRUD, system prompt editor |
| `KnowledgeView` | knowledge | file list, upload, ingest trigger |
| `FoldersView` | folders | folder CRUD, sandbox path, behavior assignment |
| `SystemView` | system | hardware stats, connector health, llama.cpp status |
| `SettingsView` | settings | .env editor, window controls config, dev mode toggle |
| `ModelHubView` | hub | hardware banner, catalog, downloads, update notifications |
| `DevLogView` | devlog | server log tail, run trace browser |

---

## Window Controls UX

Configurable via settings / `.env`:
- `WINDOW_CONTROLS_STYLE=windows|mac`
- `WINDOW_CONTROLS_SIDE=left|right`
- `WINDOW_CONTROLS_ORDER=minimize,maximize,close` (any permutation)

---

## Tauri Helpers (Desktop Only)

Invoked via `@tauri-apps/api/core`:

| command | purpose |
|---------|---------|
| `get_settings` | reads `.env` without backend |
| `save_settings` | writes `.env` without backend |
| `pick_directory` | native folder picker dialog |
| `pick_file` | native file picker (e.g. llama-server.exe) |
| `restart_agent` | kills and respawns Python sidecar |
| `stop_agent` | kills Python sidecar |

---

## System Telemetry (`/stats`)

Returns:
- CPU percent, RAM total/used/percent
- VRAM total/used/percent + per-GPU list (when NVIDIA GPU detected via `nvidia-smi`)
- Disk total/used/percent + per-disk entries (Windows drive letters)

---

## Legacy Architecture (Compatibility)

`frontend/` (Next.js) + `mcp_server.py` + optional n8n webhook orchestration still present in repo. Desktop mode is primary.
