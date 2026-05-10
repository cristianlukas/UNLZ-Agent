# Flows — UNLZ Agent

> Flujos de usuario y del sistema. Última actualización: 2026-05-02.

## Flujo: Bootstrap al inicio

1. `agent_server.py` arranca → `_startup_bootstrap()`
2. `_bootstrap_locked_runtime()` fuerza config:
   - `AGENT_HARNESS=opencode`, `LLM_PROVIDER=llamacpp`, `AGENT_EXECUTION_MODE=autonomous`
   - Detecta hardware (VRAM/RAM) → bucket (cpu/gpu_4/gpu_8/gpu_12/gpu_16/gpu_24/gpu_32)
   - Lee `_default_hardware_plan()` o `UNLZ_HARDWARE_MODEL_PLAN_JSON` → selecciona modelo por bucket
   - Verifica si modelo existe en disco. Si no, descarga desde HuggingFace
   - Verifica SHA256 si está configurado
   - Escribe `LLAMACPP_MODEL_PATH`, `LLAMACPP_MODEL_ALIAS` en `.env`
3. Si `UNLZ_OPENCODE_WARMUP_ON_STARTUP=1` (default): ejecuta `_run_opencode_warmup_once()` en background
4. Estado de bootstrap accesible vía `GET /bootstrap/status`

## Flujo: Chat con streaming

1. Usuario escribe mensaje en ChatView
2. `streamChat()` envía `POST /chat` a agent_server.py (puerto 7719)
   - Body: `{ message, history, system_prompt, mode, conversation_id, tools_mode, internet_enabled, user_profile, ... }`
3. Backend:
   - Crea `run_id`, registra `cancel_event`
   - Emite `run` event con run_id
   - Emite `timeline` event (understanding → reading → planning → editing → validating → generating → done)
   - Inyecta user profile si existe (experience_level, detail_level, language)
   - Construye prompt con `_build_opencode_prompt()`: system + behavior + history + tool policy + internet policy
   - Ejecuta `_opencode_stream()`:
     - Verifica opencode instalado
     - Resuelve workdir (sandbox_root o runtime root)
     - Verifica/opera llama.cpp server
     - Genera config opencode local aislado
     - Ejecuta `opencode run --dir <workdir> <prompt>` como subprocess
     - Pump stdout/stderr a queue async
     - Parsea JSON si `--format json` soportado, sino text raw
     - Emite SSE: `step`, `chunk`, `error`, `done`
   - Intercepta errors: `explain_error_for_humans()` traduce a mensaje humano con causas y fix steps
   - Persiste trace en `data/runs/{run_id}.json`
4. Desktop UI:
   - `streamChat()` recibe events y actualiza Zustand store
   - ChatView renderiza chunks en tiempo real
   - Timeline muestra stages visuales

## Flujo: Onboarding

1. App.tsx carga `GET /health/onboarding` + `GET /newbie/profile`
2. Si `onboardingCompleted=false`: muestra `OnboardingModal`
3. Modal muestra checks:
   - Provider opencode (instalado?)
   - Backend 7719 (activo?)
   - MCP 8000 (disponible?)
   - Escritura en data/ (permisos?)
   - RAG Chroma (índice inicializado?)
4. Botón "Dejar todo listo" → `POST /health/onboarding/fix`:
   - Crea dirs necesarios, asegura harness dirs
5. Botón "Iniciar MCP" → `POST /system/mcp/start`:
   - Ejecuta `python mcp_server.py` como subprocess detached
6. Polling de warmup status cada 3s: `GET /opencode/warmup`
7. Usuario cierra modal → guarda `onboarding_completed=true` en newbie profile

## Flujo: Conversaciones

1. Crear: `ConversationSidebar` → `createConversation()` → nuevo ID, título auto desde primer mensaje
2. Listar: sidebar muestra `conversations[]` del store
3. Seleccionar: `setActiveConv()` → ChatView carga mensajes de conversación activa
4. Eliminar: `deleteConversation()` → limpia de store, si era activa selecciona siguiente
5. Renombrar: `renameConversation()` → actualiza título
6. Asociar carpeta: `setConversationFolder()` → vincula folderId a conversación
7. Persistencia: Zustand persiste en localStorage (`unlz-agent2-store`)

## Flujo: Behaviors

1. Default: 3 behaviors (Asistente UNLZ, Dev/Código, Investigación)
2. `GET /local/behaviors` → lee `data/local_behaviors.json`
3. Store: `createBehavior()`, `updateBehavior()`, `deleteBehavior()`
4. `upsertBehaviors()` → merge con behaviors locales del backend
5. `mergeDefaultBehaviors()` → asegura que defaults no se pierdan al merge
6. Al eliminar behavior: limpia referencia en conversaciones y carpetas vinculadas

## Flujo: Folders

1. `createFolder(name)` → nuevo ID, timestamps
2. `updateFolder(id, updates)` → merge de updates
3. `deleteFolder(id)` → limpia referencia en conversaciones vinculadas
4. Conversación puede asociarse a folder → `setConversationFolder(convId, folderId)`
5. Folder se pasa como `sandbox_root` en chat request para opencode

## Flujo: Settings

1. `GET /settings` → lee `.env` como flat map
2. `POST /settings` → escribe keys en `.env` (excluye `_LOCKED_ENV_KEYS`)
3. `_LOCKED_ENV_KEYS`: `AGENT_HARNESS`, `AGENT_EXECUTION_MODE`, `LLM_PROVIDER`, `LLAMACPP_EXECUTABLE`, `LLAMACPP_MODEL_PATH`, `LLAMACPP_MODEL_ALIAS`
4. `_reload_config_runtime()` → recarga `AGENT_LANGUAGE`, `AGENT_EXECUTION_MODE`, `HARNESS_OPENCODE_BIN`

## Flujo: Dev Tools

1. `GET /dev/log?lines=300` → tail de `agent_server.log`
2. `GET /dev/log/stream` → SSE stream de log en tiempo real (poll cada 1s)
3. `GET /dev/traces?limit=30` → lista de run traces (metadata + errors)
4. `GET /dev/traces/{run_id}` → trace completo con todos los events
5. `DELETE /dev/traces` → limpia todos los traces

## Flujo: Stats + Health Center

1. `GET /stats` → CPU, RAM, métricas de runs (success rate, avg duration, etc.)
2. `GET /health/center` → estado completo: provider, model alias, opencode version, bootstrap status, recent errors
3. `GET /newbie/profile` → perfil de usuario (language, experience_level, detail_level)
4. `POST /newbie/profile` → guarda/merge perfil
5. `POST /newbie/snapshot` → guarda snapshot timestamped

## Flujo: llama.cpp Management

1. `POST /llamacpp/start` → `_ensure_llamacpp_server_started()`:
   - Si ya running → ready
   - Si no → inicia `llama-server.exe` con config actual
   - Poll hasta timeout (default 25s, 40s en warmup)
2. `POST /llamacpp/stop` → `_stop_llamacpp_server()`:
   - Kill subprocess + taskkill en Windows
3. `_llamacpp_server_url()` → `http://{LLAMACPP_HOST}:{LLAMACPP_PORT}/v1`

## Flujo: Opencode Config

1. `_ensure_opencode_local_config()` genera config en `data/.unlz_internal/opencode_home/.config/opencode/opencode.json`:
   - Provider: `unlz-llama-local` con base URL de llama.cpp
   - Model: alias de `LLAMACPP_MODEL_ALIAS`
   - Compaction: auto + prune, 30k reserved
2. Al ejecutar opencode: fuerza `HOME`, `USERPROFILE`, `XDG_CONFIG_HOME` al home aislado
3. `UNLZ_OPENCODE_CONFIG` apunta al config local

## Flujo: Cancel de Run

1. `POST /runs/{run_id}/cancel` → `_set_run_cancel(run_id)`
2. `_opencode_stream()` detecta `cancel_event.is_set()` → kill PID tree
3. Emite `error` + `done` events
4. `_unregister_run_cancel()` limpia el event del registry
