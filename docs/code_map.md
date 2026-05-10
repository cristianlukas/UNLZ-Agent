# Code Map — UNLZ Agent

> Mapa de código y responsabilidades por archivo. Última actualización: 2026-05-02.

---

## Backend (Python)

### `agent_server.py` (~2154 líneas)
Servidor FastAPI opencode-only. Arquitectura simplificada: cada request se ejecuta como subprocess de opencode con streaming SSE.

| Sección (líneas aprox.) | Responsabilidad |
|---|---|
| 1-66 | Bootstrap: runtime root, logging a archivo, imports |
| 67-134 | Helpers de configuración: `.env` reload, upsert de settings, keys bloqueadas |
| 135-292 | Hardware detection: `_detect_hardware_tier()`, `_hardware_bucket()`, `_default_hardware_plan()` |
| 293-372 | Bootstrap runtime: `_bootstrap_locked_runtime()` — fuerza config opencode/llamacpp, detecta hardware, selecciona modelo, descarga si falta |
| 373-525 | Download + model management: `_download_hf_file()`, `_sha256_file()`, `_resolve_download_target()`, estado de bootstrap |
| 526-555 | HTTP helpers: `_http_reachable()`, `_opencode_config_path()`, `_opencode_selected_base_url()` |
| 556-675 | llama.cpp server management: `_ensure_llamacpp_server_started()`, `_stop_llamacpp_server()` |
| 676-733 | Opencode warmup: `_run_opencode_warmup_once()` — ejecuta warmup al inicio |
| 734-814 | Data paths + run cancel: `_runs_dir()`, `_trace_path()`, `_persist_trace()`, `_register_run_cancel()` |
| 815-855 | Local behaviors: `_load_local_behaviors()` — lee `data/local_behaviors.json` |
| 856-928 | Harness meta + opencode config: `_ensure_opencode_local_config()` — genera config opencode con provider llamacpp |
| 929-992 | npm + opencode helpers: `_opencode_bin()`, `_opencode_version()`, `_opencode_installed()` |
| 993-1092 | Process management + SSE helpers: `_kill_pid_tree()`, `_strip_ansi()`, `_sse()`, `_timeline_stage_for_step()` |
| 1093-1135 | Prompt builder: `_build_opencode_prompt()` — arma prompt con system, history, tool policy, confusion detection |
| 1136-1440 | **`_opencode_stream()`** — ejecuta opencode como subprocess, pump stdout/stderr a queue, parsea JSON/text, emite SSE chunks |
| 1441-1452 | FastAPI app: CORS, middleware |
| 1453-1475 | Startup: `_startup_bootstrap()` — ejecuta bootstrap locked runtime + warmup en background |
| 1476-1492 | Pydantic models: `ChatRequest`, `HarnessInstallRequest`, `OnboardingActionRequest` |
| 1498-1627 | **`_chat_streaming_response()`** — endpoint principal de chat con tracing, timeline, user profile, error explanation |
| 1628-1638 | Chat endpoints: `POST /chat`, `/chat/stream`, `/api/chat`, `/api/chat/stream` |
| 1639-1638 | Cancel runs: `POST /runs/{run_id}/cancel` |
| 1642-1723 | Health + onboarding: `GET /health`, `GET /health/onboarding`, `POST /health/onboarding/fix` |
| 1724-1770 | MCP management: `POST /system/mcp/start`, `POST /system/mcp/stop` |
| 1771-1807 | llama.cpp + warmup endpoints: `POST /llamacpp/start`, `POST /llamacpp/stop`, `GET/POST /opencode/warmup` |
| 1808-1837 | Newbie templates: `GET /newbie/task-templates` |
| 1838-1872 | Settings: `GET/POST /settings`, `GET /bootstrap/status` |
| 1873-1904 | Local behaviors + harnesses: `GET /local/behaviors`, `GET /harnesses/status`, `POST /harnesses/install` |
| 1944-1999 | Dev log: `GET /dev/log`, `GET /dev/log/stream` |
| 2002-2055 | Traces: `GET /dev/traces`, `GET /dev/traces/{run_id}`, `DELETE /dev/traces` |
| 2057-2106 | Stats + newbie profile: `GET /newbie/profile`, `POST /newbie/profile`, `POST /newbie/snapshot`, `GET /health/center`, `GET /stats` |
| 2142-2154 | Root endpoint + entrypoint: `GET /`, `uvicorn.run()` |

**Funciones clave:**
- `_bootstrap_locked_runtime()` — fuerza config opencode/llamacpp, detecta hardware, selecciona modelo por bucket VRAM, descarga desde HuggingFace si no existe
- `_ensure_llamacpp_server_started()` — inicia llama.cpp como subprocess si no está running
- `_opencode_stream()` — ejecuta opencode como subprocess, pump stdout/stderr, parsea JSON/text, emite SSE
- `_chat_streaming_response()` — endpoint SSE principal con tracing, timeline, user profile, error explanation
- `_build_opencode_prompt()` — arma prompt con system, history, tool policy, internet policy, confusion detection

### `config.py` (~33 líneas)
Configuración mínima. Solo settings esenciales:
- `AGENT_LANGUAGE`, `AGENT_EXECUTION_MODE`, `HARNESS_OPENCODE_BIN`
- `BASE_DIR`, `DATA_DIR` — rutas
- `WINDOW_CONTROLS_*` — UI de ventana

### `opencode_1_catalog.py`
Catálogo de perfiles opencode. `load_opencode_1_profiles()` lee perfiles desde `launcher_profiles.json`.

### `mcp_server.py`
Servidor MCP independiente (puerto 8000). Se inicia/detiene desde el backend.

---

## Guardrails

### `guardrails/validator.py` (~83 líneas)
Validación Pydantic de input/output.

| Función | Responsabilidad |
|---|---|
| `AgentQuery` | Valida queries: detecta jailbreak/injection patterns |
| `AgentResponse` | Valida respuestas: no vacías, sources válidos |
| `validate_input(query)` | Retorna `{valid, query}` o `{valid, error}` |
| `validate_output(content, sources)` | Retorna `{valid, content, sources}` o `{valid, error}` |
| `explain_error_for_humans(error_text)` | Traduce errores técnicos a mensajes humanos con causas comunes y pasos de fix |

---

## Desktop UI (Tauri + React)

### `desktop/src/App.tsx` (~163 líneas)
Componente principal. Maneja:
- Health polling del backend cada 5s
- Carga de behaviors locales
- Carga de onboarding status + newbie profile
- Polling de warmup status cada 3s
- Onboarding modal: fix, start MCP, close
- Routing entre vistas: chat, behaviors, folders, settings, devlog

### `desktop/src/lib/store.ts` (~379 líneas)
Zustand store con persistencia.

| Sección | Campos clave |
|---|---|
| Navigation | `view`, `setView` |
| Agent status | `agentReady`, `llmReady`, `llmState`, `provider`, `modelAlias` |
| Conversations | `conversations[]`, `activeConvId`, CRUD operations, `autoTitle()` |
| Behaviors | `behaviors[]`, CRUD, `mergeDefaultBehaviors()` |
| Folders | `folders[]`, CRUD |
| Dev mode | `devMode` |
| Newbie UX | `uiMode`, `onboardingCompleted`, `newbieProfile` |

3 behaviors por defecto: Asistente UNLZ, Dev/Código, Investigación.

### `desktop/src/lib/api.ts`
Capa de comunicación con backend.

| Función | Endpoint |
|---|---|
| `streamChat()` | `POST /chat` (SSE) |
| `getHealth()` | `GET /health` |
| `getOnboardingHealth()` | `GET /health/onboarding` |
| `runOnboardingFix()` | `POST /health/onboarding/fix` |
| `startMcpServer()` | `POST /system/mcp/start` |
| `stopMcpServer()` | `POST /system/mcp/stop` |
| `getSettings()` | `GET /settings` |
| `saveSettings()` | `POST /settings` |
| `getLocalBehaviors()` | `GET /local/behaviors` |
| `getHarnessesStatus()` | `GET /harnesses/status` |
| `installHarness()` | `POST /harnesses/install` |
| `getBootstrapStatus()` | `GET /bootstrap/status` |
| `getOpencodeWarmupStatus()` | `GET /opencode/warmup` |
| `runOpencodeWarmup()` | `POST /opencode/warmup` |
| `getNewbieProfile()` | `GET /newbie/profile` |
| `saveNewbieProfile()` | `POST /newbie/profile` |
| `getNewbieTaskTemplates()` | `GET /newbie/task-templates` |
| `createNewbieSnapshot()` | `POST /newbie/snapshot` |
| `getHealthCenter()` | `GET /health/center` |
| `getStats()` | `GET /stats` |
| `getLog()` | `GET /dev/log` |
| `getLogStream()` | `GET /dev/log/stream` |
| `getTraces()` | `GET /dev/traces` |
| `getTrace()` | `GET /dev/traces/{run_id}` |
| `clearTraces()` | `DELETE /dev/traces` |
| `llamacppStart()` | `POST /llamacpp/start` |
| `llamacppStop()` | `POST /llamacpp/stop` |
| `cancelRun()` | `POST /runs/{run_id}/cancel` |

### `desktop/src/lib/types.ts`
Interfaces TypeScript:
- `View`: `"chat" | "behaviors" | "folders" | "settings" | "devlog"`
- `UiMode`: `"simple" | "advanced"`
- `AgentStep`, `ChatMessage`, `Behavior`, `Conversation`, `Folder`
- `HealthResponse`, `HealthComponent`, `OnboardingStatus`, `OnboardingCheck`
- `SystemStats`, `KbFile`, `LlamacppStatus`
- `BootstrapState`, `WarmupState`
- `TraceEntry`, `TraceEvent`

### `desktop/src/components/` (8 componentes)
| Componente | Responsabilidad |
|---|---|
| `ChatView.tsx` | Vista principal de chat — input, mensajes, streaming, timeline |
| `SettingsView.tsx` | Configuración — settings, behaviors, advanced |
| `FoldersView.tsx` | Gestión de carpetas |
| `BehaviorsView.tsx` | Creación y edición de behaviors |
| `DevLogView.tsx` | Log tail y traces de ejecución |
| `ConversationSidebar.tsx` | Navegación de conversaciones, crear/eliminar |
| `TitleBar.tsx` | Barra de título con health indicator, controls de ventana |
| `OnboardingModal.tsx` | Modal de onboarding: checks, fix, start MCP, warmup |

---

## Legacy UI (Next.js — no recomendado)

### `frontend/`
Marcado como legacy. No se recomienda extender.

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
| `data/local_behaviors.json` | Behaviors del sistema |
| `data/runs/` | Trazas de ejecución por corrida |
| `data/snapshots/` | Snapshots de estado de conversación |
| `data/newbie_profile.json` | Perfil de usuario newbie |
| `data/newbie_metrics.json` | Métricas de uso newbie |
| `data/.unlz_internal/harnesses/` | Meta de harnesses instalados |
| `data/.unlz_internal/opencode_home/` | Home directory aislado para opencode |
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
