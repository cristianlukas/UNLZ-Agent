# Project Documentation — UNLZ Agent

> Memoria técnica del proyecto. Última actualización: 2026-05-02.

---

## Visión

UNLZ Agent es un asistente de IA local opencode-only. Arquitectura simplificada: backend ejecuta opencode como subprocess con streaming SSE, llama.cpp como servidor de modelo local. Bootstrap automático: detecta hardware, descarga modelo, genera config, ejecuta warmup.

---

## Stack

### Backend
- Python 3.12+
- FastAPI + uvicorn
- Pydantic, python-dotenv, psutil

### Desktop UI (recomendada)
- Tauri v2 (Rust)
- React 18.3 + TypeScript 5
- Vite v6
- Zustand v5 (state management)
- Tailwind CSS v3

### Legacy UI (no recomendado)
- Next.js 16.1.6 (App Router)
- React 19.2.3
- Tailwind CSS v4

### Rust Tauri Native
- tauri v2
- rfd 0.15 (file/folder dialogs)
- Release profile: lto, strip, opt-level=s

---

## Configuración

Vars de entorno en `.env.example` y `config.py`.

| Variable | Default | Descripción |
|---|---|---|
| `AGENT_LANGUAGE` | `es` | en \| es \| zh |
| `AGENT_EXECUTION_MODE` | `autonomous` | confirm \| autonomous |
| `HARNESS_OPENCODE_BIN` | — | Path a opencode (auto-detect si vacío) |
| `LLAMACPP_EXECUTABLE` | — | Path a llama-server.exe |
| `LLAMACPP_MODEL_PATH` | — | Path al modelo GGUF |
| `LLAMACPP_MODEL_ALIAS` | `local-model` | Alias del modelo |
| `LLAMACPP_HOST` | `127.0.0.1` | Host de llama.cpp |
| `LLAMACPP_PORT` | `8081` | Puerto de llama.cpp |
| `LLAMACPP_CONTEXT_SIZE` | `8192` | Tamaño de contexto |
| `LLAMACPP_N_GPU_LAYERS` | `999` | Capas en GPU |
| `LLAMACPP_FLASH_ATTN` | — | Flash attention |
| `LLAMACPP_EXTRA_ARGS` | — | Args adicionales para llama.cpp |
| `LLAMACPP_MODELS_DIR` | — | Directorio de modelos GGUF |
| `UNLZ_PROJECT_ROOT` | — | Override del directorio raíz |
| `UNLZ_OPENCODE_WARMUP_ON_STARTUP` | `1` | Ejecutar warmup al inicio |
| `UNLZ_OPENCODE_PROFILES_FILE` | — | Path a launcher_profiles.json |
| `UNLZ_HARDWARE_MODEL_PLAN_JSON` | — | Override del plan de hardware |
| `OPENCODE_FIRST_CHUNK_TIMEOUT_SEC` | `35` | Timeout primer token opencode |
| `OPENCODE_SILENT_TIMEOUT_SEC` | `900` | Timeout silencioso opencode |
| `OPENCODE_WARMUP_TIMEOUT_SEC` | `480` | Timeout warmup opencode |
| `WINDOW_CONTROLS_STYLE` | `windows` | windows \| mac |
| `WINDOW_CONTROLS_SIDE` | `right` | left \| right |
| `WINDOW_CONTROLS_ORDER` | `minimize,maximize,close` | Orden de controles |

Keys bloqueadas (no modificables desde UI): `AGENT_HARNESS`, `AGENT_EXECUTION_MODE`, `LLM_PROVIDER`, `LLAMACPP_EXECUTABLE`, `LLAMACPP_MODEL_PATH`, `LLAMACPP_MODEL_ALIAS`.

---

## Estructura de archivos

```
├── agent_server.py          # Backend principal (~2154 líneas)
├── config.py                # Configuración mínima (~33 líneas)
├── opencode_1_catalog.py    # Catálogo de perfiles opencode
├── mcp_server.py            # Servidor MCP (puerto 8000)
├── requirements.txt         # Dependencias Python
├── .env.example             # Referencias de vars de entorno
├── AGENTS.md                # Reglas de trabajo del agente
├── project_documentation.md # Esta memoria
├── docs/                    # Documentación
│   ├── ARCHITECTURE.md      # Arquitectura del sistema
│   ├── API.md               # Referencia de API
│   ├── code_map.md          # Mapa de código
│   ├── decisions.md         # Decisiones técnicas
│   ├── flows.md             # Flujos de usuario/sistema
│   └── refactor_notes.md    # Notas de refactorización
├── desktop/                 # UI de escritorio (Tauri + React)
│   ├── src/
│   │   ├── App.tsx          # Componente principal
│   │   ├── main.tsx         # Entry point
│   │   ├── index.css        # Estilos globales
│   │   ├── components/      # 8 componentes React
│   │   └── lib/
│   │       ├── api.ts       # Capa API (fetch + SSE)
│   │       ├── store.ts     # Zustand store
│   │       └── types.ts     # Interfaces TypeScript
│   └── src-tauri/           # Rust Tauri native
├── frontend/                # Legacy Next.js UI (no recomendado)
├── guardrails/
│   └── validator.py         # Validación Pydantic + error explanation
├── data/                    # Archivos de datos
│   ├── local_behaviors.json # Behaviors del sistema
│   ├── runs/                # Trazas de ejecución
│   ├── snapshots/           # Snapshots de conversación
│   ├── newbie_profile.json  # Perfil de usuario
│   ├── newbie_metrics.json  # Métricas de uso
│   └── .unlz_internal/      # Harnesses, opencode home aislado
└── rag_storage/             # Base de vectores ChromaDB
```

---

## Comandos

### Desarrollo
```bash
python agent_server.py           # Backend
.\start-desktop.ps1              # Desktop dev
python mcp_server.py             # MCP server
```

### Build
```bash
cd desktop && npm run build      # Desktop
cd desktop && npm run tauri build # Tauri
```

### Validación
```bash
python -m py_compile agent_server.py
npx tsc --noEmit --project desktop/tsconfig.json
```

---

## Flujos clave

### Bootstrap
1. Detecta hardware (VRAM/RAM) → bucket
2. Selecciona modelo por bucket → descarga si falta
3. Genera config opencode local aislado
4. Ejecuta warmup en background

### Chat
1. `POST /chat` → `_chat_streaming_response()`
2. Construye prompt: system + behavior + history + policy + user profile
3. Ejecuta opencode como subprocess → llama.cpp
4. Stream SSE: run → timeline → step → chunk → error → done
5. Persiste trace en `data/runs/`

### Onboarding
1. Modal con checks de salud: provider, backend, MCP, data dir, RAG
2. Fix: crea dirs necesarios
3. Start MCP: inicia subprocess detached
4. Warmup polling: status cada 3s

---

## Decisiones técnicas recientes

- **2026-05-02**: Refactor a opencode-only. Removido: multi-provider, multi-harness, task router, model hub, RAG pipeline, advanced mode, plan/iterate modes. agent_server.py: ~8765 → ~2154 líneas
- **2026-05-02**: Bootstrap automático: hardware detection, model download, config generation, warmup
- **2026-05-02**: Home directory aislado para opencode: `data/.unlz_internal/opencode_home/`
- **2026-05-02**: Newbie UX: onboarding modal, user profile, task templates, metrics
- **2026-05-02**: Error explanation: `explain_error_for_humans()` traduce errores técnicos a mensajes humanos
- **2026-05-02**: Config keys bloqueadas: `_LOCKED_ENV_KEYS` previene modificación de settings críticos

---

## Limitaciones conocidas

- `agent_server.py` es un archivo único: ~2154 líneas, manejable pero sin separación de módulos
- No hay tests automatizados
- La legacy UI (`frontend/`) no se recomienda para nuevo trabajo
- RAG con ChromaDB almacena datos en `rag_storage/` sin límite configurado
- No hay autenticación en el backend (diseñado para uso local)
- Opencode se ejecuta como subprocess nuevo por cada request (no persistente)
- Solo soporta opencode como harness (native, little-coder, claude-code removidos)
- Solo soporta llamacpp como provider (ollama, openai removidos)
