# Architecture - UNLZ Agent

> Arquitectura del sistema. Complementa docs/ARCHITECTURE.md existente.

## Capas del sistema

PRESENTATION LAYER
  Desktop UI (Tauri + React 18)     Legacy UI (Next.js 16)
  Zustand store                     (legacy, no recommended)
        | HTTP/SSE                       | HTTP/SSE
        v                                v
APPLICATION LAYER - agent_server.py (FastAPI)
  Chat (SSE)  Actions (policy)  Model Hub  Knowledge (RAG)
  Router (area)  Harness (modes)  Dev (logs)  Advanced (gated)
        |
INFRASTRUCTURE LAYER
  LLM Providers    Vector Store    MCP Server    Guardrails
    |                  |               |              |
  ollama            chroma         port 8000    Pydantic
  llamacpp          supabase
  openai

## Dependencias entre capas

### Presentation to Application
- Desktop UI -> agent_server.py por HTTP REST + SSE streaming (puerto 7719)
- Legacy UI -> mismo backend por HTTP
- Tauri native -> filesystem operations via rfd crate (dialogs de archivos/carpetas)

### Application to Infrastructure
- agent_server.py -> LLM providers (ollama/llamacpp/openai) por OpenAI-compatible API
- agent_server.py -> Vector store (chroma/supabase) via LangChain abstractions
- agent_server.py -> MCP tools (filesystem, RAG, web search) via subprocess
- agent_server.py -> Guardrails (Pydantic validators) inline

### Data persistence
- data/ - archivos JSON/JSONL para configuracion, metrics, memoria, runs, snapshots
- rag_storage/ - ChromaDB vector store (persistente en disco)
- .env - configuracion de entorno (excluido de git)

## Flujos de datos principales

### Chat to LLM to Response
User input -> Desktop UI
  -> POST /chat (SSE)
    -> agent_server.py
      -> LangChain Chat model (ollama/llamacpp/openai)
        -> Tool-calling loop
          -> MCP tools (filesystem, RAG, web search)
          -> Guardrails validation
        -> Streaming response
      -> SSE events (run, step, chunk, confidence, done)
    -> Desktop UI streaming renderer
      -> Zustand store update
      -> UI re-render

### RAG pipeline
PDF file -> POST /knowledge/ingest
  -> rag_pipeline/ingest.py
    -> PyPDFLoader (load)
    -> RecursiveCharacterTextSplitter (1000/200)
    -> Vector store upsert (chroma/supabase)

User query -> POST /chat
  -> rag_pipeline/retriever.py
    -> Similarity search (k=3)
    -> Context injection into LLM prompt

### Model Hub
hub_catalog.py (static catalog)
  -> GET /hub/catalog
  -> GET /hub/search?q=...
  -> POST /hub/start-download -> HuggingFace API
  -> GET /hub/download-progress/<id>
  -> POST /hub/apply-model -> update .env

## Configuración de LLM providers

| Provider | URL | Modelo | Managed |
|---|---|---|---|
| ollama | OLLAMA_BASE_URL (default 11434) | OLLAMA_MODEL | External process |
| llamacpp | LLAMACPP_SERVER_URL (default 8080) | LLAMACPP_MODEL | Subprocess managed |
| openai | OPENAI_BASE_URL (default 12391/v1) | OPENAI_MODEL | External service |

Managed subprocess (llamacpp):
- llamacpp_start() - inicia llama.cpp server como subprocess
- llamacpp_stop() - kill subprocess
- llamacpp_status() - check PID y health
- llamacpp_installer_run() - descarga y configura llama.cpp

## Agent harnesses

Perfiles de comportamiento del agente:

| Harness | Descripcion |
|---|---|
| opencode (default) | Tool-calling loop con planning y execution modes |
| native | LangChain native tool-calling |
| little-coder | Modo simplificado para tareas de código |
| claude-code | Compatible con estilo Claude Code |

## Chat modes

| Mode | Descripcion |
|---|---|
| normal | Chat estándar con tool-calling |
| plan | Planning explícito: plan -> ejecutar -> validar -> reintentar |
| iterate | Iteración guiada con retroalimentación |
| simple | Sin tool-calling, respuesta directa |

## Model routing

Sistema de routing basado en áreas:
- task_router.json - mapea áreas (code, research, general, etc.) a modelos recomendados
- router_metrics.jsonl - registra accuracy y latency por área/modelo
- POST /router/recalibrate - recalibra el router con métricas acumuladas
- UI muestra heatmap de rendimiento por combinación area->modelo

## Advanced Mode

Gated por UNLZ_ADVANCED_MODE=1. Seis feature groups:

1. Profiles - perfiles de sistema (low/mid/high) con limits de tokens y timeouts
2. Benchmarks - evaluación de rendimiento de modelos (accuracy, latency, cost)
3. Prompt Presets - plantillas de system prompt editables desde UI
4. Hardware Detection - detección automática de GPU/VRAM/RAM/disco
5. Launch History - historial de inicios del agente con timestamps
6. Health Monitoring - monitoreo de salud del sistema (CPU, RAM, disco, procesos)
