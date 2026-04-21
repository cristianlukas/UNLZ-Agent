# Setup Guide (Desktop): UNLZ Agent

[🇬🇧 English](setup_guide.md) | [🇪🇸 Español](setup_guide_ES.md)

This guide covers the recommended current flow: Tauri desktop app + `agent_server.py`.

## 1. Requirements

- Windows 10/11
- Python 3.10+
- Node.js 18+
- Rust (cargo toolchain)

## 2. First-time setup

From repository root:

```powershell
.\setup-desktop.ps1
```

This script:
- installs/checks Rust
- creates `venv` and installs `requirements.txt`
- installs `desktop/` dependencies
- generates placeholder Tauri icons if needed
- creates `.env` from `.env.example` when missing

## 3. Configure `.env`

Minimal llama.cpp example:

```env
LLM_PROVIDER=llamacpp
AGENT_LANGUAGE=es
AGENT_EXECUTION_MODE=confirm
WEB_SEARCH_ENGINE=google
WINDOW_CONTROLS_STYLE=windows
WINDOW_CONTROLS_SIDE=right
WINDOW_CONTROLS_ORDER=minimize,maximize,close
LLAMACPP_EXECUTABLE=C:\path\to\llama-server.exe
LLAMACPP_MODEL_PATH=C:\path\to\model.gguf
LLAMACPP_MODEL_ALIAS=my-model
LLAMACPP_HOST=127.0.0.1
LLAMACPP_PORT=8080
```

## 4. Run

```powershell
.\start-desktop.ps1
```

Notes:
- `agent_server.py` listens on `http://127.0.0.1:7719`
- startup script cleans stale listeners on `1420` and `7719`

## 4.1 Single installer build (.exe)

```powershell
.\build_exe.bat
```

Expected output:
- `dist-single-exe\UNLZ-Agent-Setup.exe`
- `UNLZ-Agent-Setup.exe` (direct copy at repo root)

This installer uses offline WebView2 mode and deploys app + backend sidecar internally.

## 5. Key features to test

- **llama.cpp model selector**:
  - auto-detected `.gguf` dropdown
  - folder button to pick `LLAMACPP_MODELS_DIR` from explorer
  - file button to pick `llama-server.exe` from explorer
  - `Install/Update llama.cpp` button to install or update automatically and auto-configure baseline paths
  - `↻` rescan button for new models while app is running
- **Plan mode**: chat button, affects first send only
- **Iterator mode**: staged autonomous execution + validation
- **Folders**:
  - create folder
  - assign conversations
  - folder prompt
  - folder-exclusive documents
- **Window controls**:
  - Windows/Mac style
  - configurable side and order

## 6. Common issues

- `network error` in chat:
  - inspect `agent_server.log`
  - restart with `start-desktop.ps1`
- empty action outputs:
  - verify `AGENT_EXECUTION_MODE`
  - use explicit action prompts
- `llama.cpp unreachable`:
  - validate executable/model/port

## 7. Legacy mode (optional)

`frontend/` + `mcp_server.py` + n8n is still available for compatibility, but it is not the primary mode.
