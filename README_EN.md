# UNLZ Agent

UNLZ Agent is a desktop app (Tauri + React) with a FastAPI backend, built around an **opencode harness** on top of a bundled local **llama.cpp** runtime.

## Current Status

- Active architecture: `desktop/` + `agent_server.py`
- Active harness: `opencode` (backend-enforced)
- Active LLM provider: `llamacpp` (backend-enforced)
- Active execution mode: `autonomous` (backend-enforced)

## Implemented Capabilities

- `llama.cpp` runtime bundled inside the `.exe` installer
- Hardware-based model auto-selection on first startup
- Automatic model download from HuggingFace
- **MTP-first** model policy (when a viable variant exists)
- Automatic per-bucket fallback when the primary download fails
- Optional `SHA256` integrity validation per plan entry
- Persisted audit data for the effective selected model

## Hardware Buckets

Policy buckets:

- `cpu` (no GPU)
- `gpu_4`
- `gpu_8`
- `gpu_12`
- `gpu_16`
- `gpu_24`
- `gpu_32`

Critical rule:

- `gpu_24` requires a `1_*` profile (`require_1_profile=true`) loaded from `OpenCode/launcher_profiles.json`.

## Main Configuration

See `.env.example`:

- `UNLZ_OPENCODE_PROFILES_FILE`
- `UNLZ_HARDWARE_MODEL_PLAN_JSON`
- `LLAMACPP_MODELS_DIR`
- `HARNESS_OPENCODE_BIN`

Audit variables written by backend:

- `UNLZ_MODEL_SOURCE_REPO`
- `UNLZ_MODEL_SOURCE_FILE`
- `UNLZ_MODEL_FALLBACK_INDEX`
- `UNLZ_MODEL_MTP_ACTIVE`

## Build

```powershell
.\4_build_exe.bat
```

What the script does:

- builds `agent_server.exe` sidecar
- syncs bundled `llama.cpp` runtime into `desktop/src-tauri/binaries/llama.cpp`
- builds single-file NSIS installer

Output:

- `dist-single-exe\UNLZ-Agent-Setup.exe`
- `UNLZ-Agent-Setup.exe` (repo root)

## Hash Script

Added:

- `tools/fill_model_sha256.py`

Usage:

```powershell
.\venv\Scripts\python.exe tools\fill_model_sha256.py --env .env.example --models-dir "D:\Models\llamacpp" --write
```

What it does:

- computes SHA256 for locally available model files
- fills `sha256` values into `UNLZ_HARDWARE_MODEL_PLAN_JSON`
- updates `.env`/`.env.example` when `--write` is provided

## Technical Documentation

- [Architecture](docs/ARCHITECTURE.md)
- [API](docs/API.md)
- [Project Documentation](project_documentation.md)
