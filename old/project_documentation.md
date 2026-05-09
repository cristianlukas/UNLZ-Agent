# Project Documentation — UNLZ Agent

> Memoria técnica del proyecto. Última actualización: 2026-04-27.

---

## Visión

UNLZ Agent es un asistente de IA local con UI de escritorio, diseñado para planificación, ejecución de tareas, investigación y uso general. Soporta múltiples LLMs locales y cloud, RAG con ChromaDB, catálogo de modelos GGUF, y un servidor MCP para integración con herramientas externas.

---

## Stack

### Backend
- Python 3.12+
- FastAPI + uvicorn
- LangChain ecosystem: langchain, langchain-community, langchain-ollama, langchain-chroma, langchain-openai
- ChromaDB (vector store local)
- Supabase (vector store opcional)
- Pydantic, OpenAI SDK, DuckDuckGo/Google search, psutil, python-dotenv, python-multipart

### Desktop UI (recomendada)
- Tauri v2 (Rust)
- React 18.3 + TypeScript 5
- Vite v6
- Zustand v5 (state management)
- Tailwind CSS v3
- lucide-react, react-markdown, react-syntax-highlighter

### Legacy UI (no recomendado para nuevo trabajo)
- Next.js 16.1.6 (App Router)
- React 19.2.3
- Tailwind CSS v4

### Rust Tauri Native
- tauri v2
- rfd 0.15 (file/folder dialogs)
- Release profile: lto, strip, opt-level=s

---

## Configuración

Todas las vars de entorno se definen en `.env.example` y se gestionan vía `config.py`.

| Variable | Default | Descripción |
|---|---|---|
| `HOST` | `127.0.0.1` | Host del servidor |
| `PORT` | `7719` | Puerto del backend |
| `LLM_PROVIDER` | `llamacpp` | ollama \| llamacpp \| openai |
| `OLLAMA_BASE_URL` | `http://127.0.0.1:11434` | URL de Ollama |
| `OLLAMA_MODEL` | `qwen3:8b` | Modelo Ollama |
| `OPENAI_BASE_URL` | `http://127.0.0.1:12391/v1` | URL OpenAI compatible |
| `OPENAI_MODEL` | `llama` | Modelo OpenAI |
| `AGENT_HARNESS` | `opencode` | opencode \| native \| little-coder \| claude-code |
| `VECTOR_DB` | `chroma` | chroma \| supabase |
| `SUPERBASE_URL` | — | URL Supabase |
| `SUPERBASE_SERVICE_KEY` | — | Key Supabase |
| `SUPERBASE_VECTOR_DIM` | `1536` | Dimensiones del vector |
| `UNLZ_ADVANCED_MODE` | `0` | Habilita 6 feature groups avanzados |

---

## Estructura de archivos

```
├── agent_server.py          # Backend principal (~7200 líneas)
├── config.py                # Gestión de configuración (.env)
├── hub_catalog.py           # Catálogo GGUF + hardware profiler (~670 líneas)
├── mcp_server.py            # Servidor MCP (puerto 8000)
├── requirements.txt         # Dependencias Python
├── .env.example             # Referencias de vars de entorno
├── AGENTS.md                # Reglas de trabajo del agente
├── project_documentation.md # Esta memoria
├── Next-Steps.md            # Hoja de ruta (inglés)
├── Next-Steps_ES.md         # Hoja de ruta (español)
├── setup-desktop.ps1        # Script de instalación
├── start-desktop.ps1        # Script de inicio en modo dev
├── docs/                    # Documentación
│   ├── ARCHITECTURE.md      # Arquitectura del sistema
│   ├── API.md               # Referencia de API
│   ├── adr/                 # Decisiones de arquitectura
│   ├── code_map.md          # Mapa de código
│   ├── decisions.md         # Decisiones técnicas
│   ├── flows.md             # Flujos de usuario/sistema
│   └── refactor_notes.md    # Notas de refactorización
├── desktop/                 # UI de escritorio (Tauri + React)
│   ├── src/
│   │   ├── App.tsx          # Componente principal
│   │   ├── main.tsx         # Entry point
│   │   ├── index.css        # Estilos globales
│   │   ├── components/      # 12 componentes React
│   │   └── lib/
│   │       ├── api.ts       # Capa API (fetch + SSE)
│   │       ├── store.ts     # Zustand store
│   │       └── types.ts     # Interfaces TypeScript
│   └── src-tauri/           # Rust Tauri native
│       ├── Cargo.toml
│       ├── build.rs
│       └── src/main.rs
├── frontend/                # Legacy Next.js UI
│   ├── app/
│   │   ├── layout.tsx
│   │   ├── page.tsx
│   │   └── api/             # API routes
│   └── components/
├── rag_pipeline/            # Pipeline RAG
│   ├── factory.py           # Factory: embeddings + vector store
│   ├── ingest.py            # Ingestión PDF
│   └── retriever.py         # Búsqueda de similitud
├── guardrails/
│   └── validator.py         # Validación Pydantic
├── data/                    # Archivos de datos
│   ├── task_router.json     # Configuración del router
│   ├── router_metrics.jsonl # Métricas del router
│   ├── telemetry.jsonl      # Datos de telemetría
│   ├── memory.jsonl         # Memoria del agente
│   ├── local_behaviors.json # Comportamientos locales
│   ├── runs/                # Trazas de ejecución
│   ├── snapshots/           # Snapshots de conversación
│   └── folders/             # Configuración de carpetas
└── rag_storage/             # Base de vectores ChromaDB
```

---

## Comandos

### Desarrollo
```bash
# Iniciar backend
python agent_server.py

# Iniciar desktop dev
.\start-desktop.ps1

# Iniciar MCP server
python mcp_server.py
```

### Build
```bash
# Desktop
cd desktop && npm run build

# Tauri
cd desktop && npm run tauri build

# Legacy frontend
cd frontend && npm run build
```

### Validación
```bash
# Python
python -m py_compile agent_server.py
ruff check agent_server.py config.py hub_catalog.py mcp_server.py

# TypeScript
npx tsc --noEmit --project desktop/tsconfig.json
npx tsc --noEmit --project frontend/tsconfig.json
```

### Scripts legacy
- `1_install.bat` — Instalar dependencias legacy
- `2_start_old.bat` — Iniciar legacy frontend
- `3_start_new.bat` — Iniciar desktop con backend
- `4_build_exe.bat` — Build portable de escritorio

---

## Flujos clave

### Chat con streaming
1. Desktop envía `POST /chat` con mensaje + historial
2. Backend ejecuta tool-calling loop con el LLM seleccionado
3. Responde con SSE: `run`, `step`, `chunk`, `confidence`, `error`, `done`
4. Desktop renderiza en tiempo real con Zustand store

### RAG
1. Usuario ingesta PDFs vía `POST /knowledge/ingest`
2. `rag_pipeline/ingest.py` carga PDF → split → vector store
3. `rag_pipeline/retriever.py` busca similitud al hacer chat
4. Resultados se inyectan en el contexto del LLM

### Model Hub
1. `hub_catalog.py` mantiene catálogo de ~100 modelos GGUF
2. `POST /hub/start-download` descarga desde HuggingFace
3. Progreso se consulta vía `GET /hub/download-progress`
4. `POST /hub/apply-model` actualiza `.env` con modelo descargado

### MCP Server
1. Ejecuta en puerto 8000 como servidor independiente
2. Expone herramientas: system stats, query safety, RAG search, folder search, web search
3. Se conecta al mismo LLM que el backend principal

### Advanced Mode (gated por `UNLZ_ADVANCED_MODE=1`)
- **Profiles**: perfiles de sistema preconfigurados (low/mid/high)
- **Benchmarks**: evaluación de rendimiento de modelos
- **Prompt Presets**: plantillas de system prompt editables
- **Hardware Detection**: detección automática de GPU/RAM/VRAM
- **Launch History**: historial de inicios del agente
- **Health Monitoring**: monitoreo de salud del sistema

---

## Decisiones técnicas recientes

- **2026-04-27**: Se creó estructura de documentación completa (AGENTS.md, project_documentation.md, docs/, skills/) para facilitar trabajo local con OpenCode
- **Advanced Mode**: Se añadieron 6 feature groups con flag `UNLZ_ADVANCED_MODE=1`. Incluye profiles, benchmarks, prompt presets, hardware detection, launch history, health monitoring
- **Desktop recomendado**: Se marcó `frontend/` como legacy. Nuevo trabajo debe ir en `desktop/`
- **Data files**: Todos los datos persistentes en `data/`, excluidos de git vía `.gitignore`
- **Rust Tauri native**: Se mantiene Cargo.toml con tauri v2 y rfd 0.15 para diálogos nativos de archivos/carpetas

---

## Limitaciones conocidas

- `agent_server.py` es un archivo único de ~7200 líneas: difícil de navegar y modificar sin riesgo
- No hay tests automatizados
- La legacy UI (`frontend/`) usa Next.js 16 con React 19, pero no se recomienda para nuevo trabajo
- El catálogo de modelos GGUF en `hub_catalog.py` requiere actualización manual periódica
- RAG con ChromaDB almacena datos en `rag_storage/` que puede crecer sin límite configurado
- No hay sistema de autenticación en el backend (diseñado para uso local)

- **2026-04-28 (latencia chat)**: Se optimizó el pipeline de `mode=normal` para consultas cortas no operacionales.
  - Nuevo fast-path heurístico (`_is_short_non_operational_query`) para forzar ruta `quick` y evitar `depth_router` LLM en preguntas simples.
  - Ajuste en detección de acciones (`_is_action_request`) para evitar falsos positivos como "cómo se hace ...".
  - `simple_chat` ahora usa historial más corto (default 4, `SIMPLE_CHAT_HISTORY_LIMIT`) y generación más liviana (`max_tokens=48`, `temperature=0.55`).
  - `SIMPLE_CHAT_TIMEOUT_SEC` ahora tiene default seguro (75s) para evitar cuelgues indefinidos.
  - Se evita `model_switch` innecesario cuando los overrides de runtime no cambian realmente la configuración activa (`_has_effective_llamacpp_overrides`).
