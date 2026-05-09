# UNLZ Agent

UNLZ Agent es una app desktop (Tauri + React) con backend FastAPI, orientada a usar **opencode harness** sobre un runtime local de **llama.cpp** bundleado.

## Estado Actual

- Arquitectura activa: `desktop/` + `agent_server.py`
- Harness activo: `opencode` (bloqueado por backend)
- Provider LLM activo: `llamacpp` (bloqueado por backend)
- Execution mode activo: `autonomous` (bloqueado por backend)

## Novedades Implementadas

- Bundle de `llama.cpp` dentro del instalador `.exe`
- Autoselección de modelo por hardware en primer arranque
- Autodescarga de modelo desde HuggingFace
- Política **MTP-first** (siempre que exista variante viable)
- Fallback automático por bucket si falla descarga principal
- Validación de integridad `SHA256` opcional por entrada
- Auditoría persistida de modelo efectivo seleccionado

## Buckets de Hardware

Buckets soportados por policy:

- `cpu` (sin GPU)
- `gpu_4`
- `gpu_8`
- `gpu_12`
- `gpu_16`
- `gpu_24`
- `gpu_32`

Regla crítica:

- En `gpu_24` se exige perfil `1_*` (`require_1_profile=true`), tomado desde `OpenCode/launcher_profiles.json`.

## Configuración Principal

Ver `.env.example`:

- `UNLZ_OPENCODE_PROFILES_FILE`
- `UNLZ_HARDWARE_MODEL_PLAN_JSON`
- `LLAMACPP_MODELS_DIR`
- `HARNESS_OPENCODE_BIN`

Variables de auditoría escritas por backend:

- `UNLZ_MODEL_SOURCE_REPO`
- `UNLZ_MODEL_SOURCE_FILE`
- `UNLZ_MODEL_FALLBACK_INDEX`
- `UNLZ_MODEL_MTP_ACTIVE`

## Build

```powershell
.\4_build_exe.bat
```

El script:

- genera `agent_server.exe` sidecar
- sincroniza runtime `llama.cpp` bundleado en `desktop/src-tauri/binaries/llama.cpp`
- compila instalador NSIS único

Salida:

- `dist-single-exe\UNLZ-Agent-Setup.exe`
- `UNLZ-Agent-Setup.exe` (raíz)

## Script de Hashes

Se agregó:

- `tools/fill_model_sha256.py`

Uso:

```powershell
.\venv\Scripts\python.exe tools\fill_model_sha256.py --env .env.example --models-dir "D:\Models\llamacpp" --write
```

Función:

- calcula SHA256 de modelos presentes
- rellena `sha256` en `UNLZ_HARDWARE_MODEL_PLAN_JSON`
- actualiza `.env`/`.env.example` si se usa `--write`

## Documentación Técnica

- [Arquitectura](docs/ARCHITECTURE.md)
- [API](docs/API.md)
- [Documentación de Proyecto](project_documentation.md)
