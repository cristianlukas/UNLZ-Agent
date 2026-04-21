![Institutional Logo](https://github.com/JonatanBogadoUNLZ/PPS-Jonatan-Bogado/blob/9952aac097aca83a1aadfc26679fc7ec57369d82/LOGO%20AZUL%20HORIZONTAL%20-%20fondo%20transparente.png)

# Universidad Nacional de Lomas de Zamora - Facultad de Ingeniería
# UNLZ Agent

[🇬🇧 English](README_EN.md) | [🇪🇸 Español](README.md)

UNLZ Agent is a local desktop assistant (Tauri + React) with a FastAPI backend, tool execution on Windows, folder-scoped context, and planning/iteration modes.

## Project Status

- Current recommended mode: `desktop/` + `agent_server.py`
- Legacy mode still available: `frontend/` (Next.js) + `mcp_server.py` + n8n

## Current Architecture (Desktop)

```mermaid
graph TD
    UI["Desktop UI (Tauri + React)"] -->|HTTP/SSE| API["agent_server.py (FastAPI) :7719"]
    API --> LLM["LLM provider (llama.cpp / Ollama / OpenAI)"]
    API --> RAG["RAG pipeline (Chroma/Supabase)"]
    API --> TOOLS["Tools: web_search, run_windows_command, stats, folder docs"]
```

Technical docs:
- [Architecture](docs/ARCHITECTURE.md)
- [API](docs/API.md)

## Main Features

- SSE chat streaming (`step`, `chunk`, `error`, `done`)
- Agent tools:
  - `search_local_knowledge`
  - `search_folder_documents`
  - `web_search` (Google/DuckDuckGo/auto)
  - `get_current_time`
  - `get_system_stats`
  - `list_knowledge_base_files`
  - `run_windows_command`
- Chat modes:
  - `normal`
  - `plan` (alternatives + final plan)
  - `iterate` (stage planning, execution, validation, retries)
- Folders:
  - group conversations
  - support base behavior + custom folder prompt
  - support folder-exclusive documents
- Action execution modes:
  - `confirm` (ask before running)
  - `autonomous` (run directly)
- Configurable window controls:
  - style `windows` or `mac`
  - side `left/right`
  - button order (`minimize/maximize/close`)
  - option to minimize to system tray on close (`MINIMIZE_TO_TRAY_ON_CLOSE`)
- llama.cpp model selector:
  - dropdown of `.gguf` models detected in model directories and subdirectories
  - folder button to pick `LLAMACPP_MODELS_DIR` from a native browser dialog
  - file button to pick `llama-server.exe` from a native browser dialog
  - `Install/Update llama.cpp` button:
    - installs llama.cpp automatically when missing
    - updates when a newer version is detected
    - auto-configures `LLAMACPP_EXECUTABLE` and baseline settings
  - `↻` button to rescan while the app is open
- System view:
  - CPU, RAM, VRAM
  - disks per drive letter (C:, D:, ...)
  - Agent Server and llama.cpp status/control
- Chat UX:
  - edit user/assistant messages
  - "Save and recalculate"
  - behavior cards for empty conversations
  - suggestion cards now keep the prefilled draft in the input after creating a new conversation

## Requirements

- Windows 10/11
- Python 3.10+
- Node.js 18+
- Rust toolchain (for Tauri)
- (Optional) llama.cpp, Ollama, OpenAI API key

## Quick Setup

From repo root:

```powershell
.\setup-desktop.ps1
```

## Run (Desktop)

```powershell
.\start-desktop.ps1
```

This starts the desktop app and local backend.

## Single-File .exe Build

From repository root:

```powershell
.\3_build_exe.bat
```

This generates a single installer at:
- `dist-single-exe\UNLZ-Agent-Setup.exe`
- `UNLZ-Agent-Setup.exe` (also copied to project root)

Installer behavior:
- one file to distribute
- installs app + backend sidecar automatically
- uses offline WebView2 installation mode (no internet required during setup)
- installer language selector enabled (Spanish/English)
- installer icon explicitly set from `desktop/src-tauri/icons/icon.ico`

## Configuration

Config is stored in `.env` (editable from UI or file):

- `LLM_PROVIDER=llamacpp|ollama|openai`
- `AGENT_LANGUAGE=es|en|zh`
- `AGENT_EXECUTION_MODE=confirm|autonomous`
- `WEB_SEARCH_ENGINE=google|duckduckgo|auto`
- `MINIMIZE_TO_TRAY_ON_CLOSE=true|false`
- `WINDOW_CONTROLS_STYLE=windows|mac`
- `WINDOW_CONTROLS_SIDE=left|right`
- `WINDOW_CONTROLS_ORDER=minimize,maximize,close` (or other permutation)
- `LLAMACPP_*`, `OLLAMA_*`, `OPENAI_*`, `SUPABASE_*`

Use `.env.example` as baseline.

## Legacy Web Mode

The `frontend/` + `mcp_server.py` + n8n stack remains in the repo for compatibility, but it is not the primary recommended workflow.

## Quick Troubleshooting

- `TypeError: network error` in UI:
  - check `agent_server.log`
  - restart with `.\start-desktop.ps1`
- empty action output:
  - verify `AGENT_EXECUTION_MODE`
  - use explicit action prompts
- `llama.cpp unreachable`:
  - verify `LLAMACPP_EXECUTABLE`, `LLAMACPP_MODEL_PATH`, port `8080`
- `web_search` with no results:
  - switch `WEB_SEARCH_ENGINE` or retry
  - backend emits explicit web-search failure message when unavailable
