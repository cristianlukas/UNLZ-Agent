# Architecture - UNLZ Agent

> Arquitectura del sistema. Última actualización: 2026-05-02.

## Visión general

UNLZ Agent es un asistente de IA local opencode-only. Arquitectura simplificada: el backend ejecuta opencode como subprocess con streaming SSE, y llama.cpp como servidor de modelo local.

```
┌─────────────────────────────────────────────────────────────────┐
│                       PRESENTATION LAYER                       │
│  Desktop UI (Tauri v2 + React 18 + Zustand + Tailwind)         │
│  Views: Chat, Behaviors, Folders, Settings, DevLog             │
│  Onboarding modal, TitleBar, ConversationSidebar               │
└──────────────────────────┬──────────────────────────────────────┘
                           │ HTTP/SSE (port 7719)
                           v
┌─────────────────────────────────────────────────────────────────┐
│                    APPLICATION LAYER                            │
│  agent_server.py (FastAPI, ~2154 líneas)                       │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │ Bootstrap: detecta hardware → selecciona modelo →        │  │
│  │   descarga si falta → config opencode → warmup           │  │
│  ├───────────────────────────────────────────────────────────┤  │
│  │ Chat: SSE streaming → opencode subprocess → llama.cpp    │  │
│  │ Prompt builder → tool/internet policy → confusion detect  │  │
│  │ User profile injection → timeline stages → error explain  │  │
│  ├───────────────────────────────────────────────────────────┤  │
│  │ Management: llama.cpp start/stop, MCP start/stop,        │  │
│  │   settings, behaviors, harnesses, traces, stats          │  │
│  └───────────────────────────────────────────────────────────┘  │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           v
┌─────────────────────────────────────────────────────────────────┐
│                    INFRASTRUCTURE LAYER                         │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │ llama.cpp    │  │ opencode     │  │ MCP Server   │          │
│  │ (port 8080)  │  │ (subprocess) │  │ (port 8000)  │          │
│  │ GGUF models  │  │ tool-calling │  │ tools        │          │
│  └──────────────┘  └──────────────┘  └──────────────┘          │
│  ┌──────────────┐  ┌──────────────┐                            │
│  │ ChromaDB     │  │ Guardrails   │                            │
│  │ (rag_storage)│  │ (Pydantic)   │                            │
│  └──────────────┘  └──────────────┘                            │
└─────────────────────────────────────────────────────────────────┘
```

## Capas del sistema

### Presentation to Application
- Desktop UI → agent_server.py por HTTP REST + SSE streaming (puerto 7719)
- Tauri native → filesystem operations via rfd crate (dialogs de archivos/carpetas)
- Zustand store → persistencia en localStorage

### Application to Infrastructure
- agent_server.py → llama.cpp por OpenAI-compatible API (port 8080)
- agent_server.py → opencode por subprocess (asyncio.create_subprocess_exec)
- agent_server.py → MCP server por HTTP (port 8000)
- agent_server.py → Guardrails inline (Pydantic validators)

### Data persistence
- `data/` — archivos JSON/JSONL para behaviors, runs, snapshots, newbie profile
- `data/.unlz_internal/` — harnesses meta, opencode home aislado
- `rag_storage/` — ChromaDB vector store (persistente en disco)
- `.env` — configuración de entorno (excluido de git)

## Bootstrap automático

Al iniciar, el backend ejecuta automáticamente:

1. **Config lock**: fuerza `AGENT_HARNESS=opencode`, `LLM_PROVIDER=llamacpp`, `AGENT_EXECUTION_MODE=autonomous`
2. **Hardware detection**: detecta VRAM/RAM → bucket (cpu, gpu_4, gpu_8, gpu_12, gpu_16, gpu_24, gpu_32)
3. **Model selection**: `_default_hardware_plan()` mapea bucket → modelo GGUF apropiado
4. **Download**: si modelo no existe en disco, descarga desde HuggingFace con SHA256 verification
5. **Config opencode**: genera config local aislado con provider llamacpp
6. **Warmup**: ejecuta opencode warmup en background (configurable con `UNLZ_OPENCODE_WARMUP_ON_STARTUP`)

## Chat flow

```
User input → Desktop UI
  → POST /chat (SSE)
    → agent_server.py
      → _chat_streaming_response()
        → _build_opencode_prompt() — system + behavior + history + policy
        → _opencode_stream()
          → opencode subprocess
            → llama.cpp (port 8080)
          → stdout/stderr pump → parse JSON/text → SSE chunks
        → timeline stages, error explanation, user profile injection
        → trace persistence
      → SSE events (run, timeline, step, chunk, error, done)
    → Desktop UI streaming renderer
      → Zustand store update
      → UI re-render
```

## Configuración de LLM

Solo llamacpp. Configuración en `.env`:

| Variable | Default | Descripción |
|---|---|---|
| `LLAMACPP_EXECUTABLE` | — | Path a llama-server.exe |
| `LLAMACPP_MODEL_PATH` | — | Path al modelo GGUF |
| `LLAMACPP_MODEL_ALIAS` | `local-model` | Alias del modelo |
| `LLAMACPP_HOST` | `127.0.0.1` | Host del servidor |
| `LLAMACPP_PORT` | `8081` | Puerto del servidor |
| `LLAMACPP_CONTEXT_SIZE` | `8192` | Tamaño de contexto |
| `LLAMACPP_N_GPU_LAYERS` | `999` | Capas en GPU |
| `LLAMACPP_FLASH_ATTN` | — | Flash attention |
| `LLAMACPP_EXTRA_ARGS` | — | Args adicionales |

Managed subprocess:
- `_ensure_llamacpp_server_started()` — inicia si no está running
- `_stop_llamacpp_server()` — kill subprocess

## Opencode integration

Opencode se ejecuta como subprocess con config aislada:

- **Home directory**: `data/.unlz_internal/opencode_home/` (aislado del usuario)
- **Config**: `opencode_home/.config/opencode/opencode.json` (generado automáticamente)
- **Environment**: `HOME`, `USERPROFILE`, `XDG_CONFIG_HOME`, `UNLZ_OPENCODE_CONFIG` apuntan al home aislado
- **Permissions**: `--dangerously-skip-permissions` si soportado
- **Format**: `--format json` si soportado
- **Streaming**: stdout/stderr pump async → parse JSON/text → SSE chunks

## ChatRequest model

```python
class ChatRequest(BaseModel):
    message: str
    history: list[dict] = []
    system_prompt: str = ""
    model_override: str = ""
    harness_override: str = ""
    llamacpp_overrides: dict = {}
    folder_id: str = ""
    sandbox_root: str = ""
    mode: str = "normal"
    conversation_id: str = ""
    dry_run: bool = False
    internet_enabled: bool = True
    tools_mode: str = "auto"       # auto | with_tools | without_tools
    user_profile: dict = {}         # experience_level, detail_level, language
```

## SSE event types

| type | payload fields | notes |
|------|---------------|-------|
| `run` | `run_id` | first event, always present |
| `timeline` | `stage`, `label`, `ts` | visual stage indicator |
| `step` | `text`, `args` | tool invocations, opencode status |
| `chunk` | `text` | streamed LLM output |
| `error` | `text`, `human_message`, `common_causes`, `fix_steps` | error con explicación humana |
| `done` | — | stream complete |

## Newbie UX

Sistema de onboarding y perfil de usuario:

- **Onboarding modal**: checks de salud, fix, start MCP, warmup status
- **User profile**: `experience_level` (newbie/beginner/intermediate/expert), `detail_level` (simple/normal/detailed), `language` (es/en)
- **Task templates**: 4 templates predefinidos (explain error, refactor, document, prepare PR)
- **Metrics**: success rate, avg duration, time to first success
- **Snapshots**: timestamped snapshots de estado

## Advanced features (removed)

Las siguientes features de versiones anteriores fueron removidas:
- Multi-provider (ollama, openai)
- Multi-harness (native, little-coder, claude-code)
- Task router con model chain
- Model hub con catálogo GGUF
- RAG pipeline con ingestión PDF
- Advanced mode con profiles, benchmarks, prompt presets
- Plan/iterate modes
