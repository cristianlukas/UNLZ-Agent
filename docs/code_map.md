# Code Map — UNLZ Agent

> Mapa de código y responsabilidades por archivo.

---

## Backend (Python)

### `agent_server.py` (~7200 líneas)
Archivo único principal. Contiene todo el servidor FastAPI.

| Sección (líneas aprox.) | Responsabilidad |
|---|---|
| 1–200 | Imports, constantes, configuraciones iniciales |
| 200–800 | Modelos Pydantic (ChatRequest, Message, AgentStep, etc.) |
| 800–1500 | Helpers: format_history, extract_thinking, extract_code_blocks |
| 1500–2500 | Tool-calling loop principal: execute_with_tools, process_tool_call |
| 2500–3500 | Modes: normal, plan, iterate, simple — lógica de planificación |
| 3500–4500 | Harnesses: opencode, native, little-coder, claude-code |
| 4500–5000 | Endpoints: chat (SSE), actions, health, config, settings |
| 5000–5700 | LlamaCPP management: start/stop/status subprocess |
| 5700–6300 | Model Hub: catalog, search, download, apply |
| 6300–6800 | Dev tools: log tail, run traces |
| 6800–7200 | Knowledge, folders, stats, router, advanced mode, lifespan |

**Funciones clave:**
- `lifespan()` — inicio/fin del FastAPI app
- `chat()` — endpoint SSE principal, tool-calling loop
- `action_run_windows_command()` — ejecución de comandos Windows con policy engine
- `health()`, `connectors_health()` — health checks
- `get_settings()`, `save_settings()` — gestión de configuración
- `llamacpp_start()`, `llamacpp_stop()`, `llamacpp_status()` — lifecycle de llama.cpp
- `hub_search()`, `hub_get_catalog()`, `hub_start_download()`, `hub_apply_model()` — model hub
- `dev_get_log()`, `dev_log_stream()`, `dev_list_traces()`, `dev_get_trace()` — debugging
- `list_files()`, `list_folder_files()` — filesystem tools via MCP
- `get_router_config()`, `save_router_config()`, `recalibrate_router()` — model routing

### `config.py`
Gestión centralizada de todas las vars de entorno.
- Lee `.env` y expone como attrs con defaults
- `save_settings()` escribe al `.env` y recarga config
- Validación de URLs, paths y valores

### `hub_catalog.py` (~670 líneas)
Catálogo curado de modelos GGUF con:
- `MODELS_CATALOG` — lista de modelos con nombre, repo, size, family, ram needed
- `hardware_profiler()` — detecta GPU (VRAM), RAM total, disco disponible
- `get_recommended_models()` — filtra catálogo según hardware
- `check_update()` — compara catálogo local vs remoto en GitHub

### `mcp_server.py`
Servidor MCP independiente (puerto 8000).
- `system_stats()` — uso de CPU, RAM, disco
- `check_query_safety()` — evalúa si una consulta es segura
- `rag_search()`, `folder_search()` — herramientas RAG y filesystem
- `web_search()` — búsqueda web integrada

---

## RAG Pipeline

### `rag_pipeline/factory.py`
Factory pattern para providers de embeddings y vector store.
- `get_embeddings(provider)` — retorna instancias de embeddings
- `get_vector_store(embeddings, provider)` — retorna ChromaDB o Supabase vector store

### `rag_pipeline/ingest.py`
Ingestión de documentos PDF.
- Carga PDFs con PyPDFLoader
- Split con RecursiveCharacterTextSplitter (1000 chars, 200 overlap)
- Upsert al vector store

### `rag_pipeline/retriever.py`
Búsqueda de similitud semántica.
- `search(query, k=3)` — retorna documentos relevantes del vector store
- Resultados se inyectan en el contexto del chat

---

## Guardrails

### `guardrails/validator.py`
Validación Pydantic de input/output del agente.
- `GuardrailInput` — valida entradas del usuario
- `GuardrailOutput` — valida salidas del LLM
- Detecta patrones prohibidos y contenido inseguro

---

## Desktop UI (Tauri + React)

### `desktop/src/App.tsx`
Componente principal. Maneja:
- Health polling del backend
- Routing entre vistas (Chat, Behaviors, Knowledge, Folders, System, Settings, ModelHub, DevLog)
- Sidebar de navegación
- Composición de componentes

### `desktop/src/lib/api.ts`
Capa de comunicación con backend.
- `streamChat()` — SSE streaming principal con AsyncGenerator
- `fetchHealth()`, `fetchSettings()`, `saveSettings()` — config
- `fetchConversations()`, `createConversation()`, `deleteConversation()` — gestión de chats
- `fetchBehaviors()`, `saveBehavior()` — behaviors
- `listFiles()`, `listFolderFiles()` — filesystem
- `hubSearch()`, `hubGetCatalog()`, `hubStartDownload()` — model hub
- `fetchRouterConfig()`, `saveRouterConfig()`, `recalibrateRouter()` — routing
- `fetchHarnessesStatus()`, `installHarness()` — harnesses
- `fetchLog()`, `fetchTraces()`, `fetchTrace()` — dev tools
- `fetchSystemStats()`, `checkQuerySafety()` — health
- `fetchKnowledgeFiles()`, `ingestKnowledge()`, `deleteKnowledge()` — RAG
- `fetchFolders()`, `saveFolder()`, `deleteFolder()` — folders
- `fetchLaunchHistory()`, `fetchBenchmarks()` — advanced mode

### `desktop/src/lib/store.ts`
Zustand store global.
- `agentState` — online/offline/idle/running/stopped/error
- `conversation`, `messages` — chat actual
- `conversations` — lista de conversaciones
- `settings` — configuración
- `behaviors` — behaviors del sistema
- `folders` — carpetas
- `hub` — estado del model hub
- `devLog`, `traces` — dev tools

### `desktop/src/lib/types.ts`
Todas las interfaces TypeScript:
- `AgentStep`, `ChatMessage`, `Behavior`, `Conversation`, `Folder`
- `HealthResponse`, `SystemStats`, `KbFile`
- `HubCatalogResponse`, `HubDownload`, `HubSearchResponse`, `HubUpdateNotification`
- `LlamacppStatus`
- `AdvancedSettings`

### `desktop/src/components/` (12 componentes)
| Componente | Responsabilidad |
|---|---|
| `ChatView.tsx` | Vista principal de chat — input, mensajes, streaming |
| `SettingsView.tsx` | Configuración — LLM, provider, harness, env vars, advanced mode |
| `ModelHubView.tsx` | Catálogo de modelos GGUF — búsqueda, descargas, aplicar |
| `KnowledgeView.tsx` | Ingestión y gestión de archivos RAG |
| `BehaviorsView.tsx` | Creación y edición de behaviors |
| `FoldersView.tsx` | Gestión de carpetas |
| `SystemView.tsx` | Health, stats, connectors, query safety |
| `DevLogView.tsx` | Log tail y traces de ejecución |
| `ConvSidebar.tsx` | Navegación de conversaciones |
| `HealthIndicator.tsx` | Indicador visual de estado del backend |
| `StreamingRenderer.tsx` | Renderizado de chunks SSE |
| `AdvancedModeSection.tsx` | UI de advanced mode (profiles, benchmarks, presets, etc.) |

---

## Legacy UI (Next.js — no recomendado)

### `frontend/app/`
- `layout.tsx` — layout base
- `page.tsx` — página principal
- `api/` — API routes proxy al backend

### `frontend/components/`
Componentes React legacy. No se recomienda extender.

---

## Rust Tauri Native

### `desktop/src-tauri/`
- `Cargo.toml` — tauri v2, rfd 0.15, release profile con lto/strip
- `build.rs` — script de build de Tauri
- `src/main.rs` — entry point Rust: inicia window, configura Tauri plugins

---

## Data Files

| Archivo | Contenido |
|---|---|
| `data/task_router.json` | Configuración del router de modelos por área |
| `data/router_metrics.jsonl` | Métricas de routing (área, modelo, accuracy, latency) |
| `data/telemetry.jsonl` | Datos de telemetría de uso |
| `data/memory.jsonl` | Memoria de largo horizonte del agente |
| `data/local_behaviors.json` | Behaviors del sistema |
| `data/runs/` | Trazas de ejecución por corrida |
| `data/snapshots/` | Snapshots de estado de conversación |
| `data/folders/` | Configuración de carpetas |
| `rag_storage/` | Base de vectores ChromaDB |

---

## Scripts

| Script | Descripción |
|---|---|
| `setup-desktop.ps1` | Setup completo: Rust, Python venv, npm deps, Tauri |
| `start-desktop.ps1` | Inicia backend + frontend en modo dev |
| `1_install.bat` | Instalar deps legacy |
| `2_start_old.bat` | Iniciar legacy frontend |
| `3_start_new.bat` | Iniciar desktop con backend |
| `4_build_exe.bat` | Build portable |
| `build-portable.ps1` | Build portable PowerShell |
