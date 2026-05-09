# API Reference - UNLZ Agent

Base URL: `http://127.0.0.1:7719`

## Health

### `GET /health`
Estado de backend y disponibilidad de opencode.

## Settings

### `GET /settings`
Lee `.env` actual.

### `POST /settings`
Guarda settings permitidos.

Notas:

- Claves críticas bloqueadas por backend (`AGENT_HARNESS`, `LLM_PROVIDER`, `AGENT_EXECUTION_MODE`, `LLAMACPP_EXECUTABLE`, `LLAMACPP_MODEL_PATH`, `LLAMACPP_MODEL_ALIAS`).
- Respuesta incluye `blocked_keys`.

## Bootstrap

### `GET /bootstrap/status`
Estado del flujo de arranque y selección de modelo.

Campos típicos:

- `status`: `idle|running|downloading|ready|warning|error`
- `detail`: descripción breve
- `tier`, `bucket`, `vram_gb`, `ram_gb`
- `model_path`
- `selected_plan`
- `selected_candidate`

## Chat

### `POST /chat`
### `POST /chat/stream`
### `POST /api/chat`
### `POST /api/chat/stream`
SSE con ejecución opencode.

Eventos SSE:

- `run`
- `step`
- `chunk`
- `error`
- `done`

## Runs / Cancel

### `POST /runs/{run_id}/cancel`
Cancela ejecución activa.

## Harnesses

### `GET /harnesses/status`
Estado de opencode.

### `POST /harnesses/install`
Instala opencode vía npm.

## Debug

### `GET /dev/log`
Tail del log.

### `GET /dev/log/stream`
Stream SSE del log.

### `GET /dev/traces`
Lista trazas de runs.

### `GET /dev/traces/{run_id}`
Detalle de traza.

### `DELETE /dev/traces`
Limpia trazas.

## Stats

### `GET /stats`
CPU y RAM.
