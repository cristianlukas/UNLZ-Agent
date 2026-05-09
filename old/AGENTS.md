# Agent Guidelines — UNLZ Agent

## Idioma y estilo

- Responder en español, salvo que el usuario pida explícitamente otro idioma.
- Mantener explicaciones claras, directas y prácticas.
- Evitar relleno, repeticiones y resúmenes innecesarios.
- Código y documentación técnica: estilo profesional y consistente.

---

## Contexto del proyecto

UNLZ Agent es un asistente de IA local con:
- **Backend**: `agent_server.py` (FastAPI, SSE, tool-calling loop, ~7200 líneas)
- **Desktop UI**: `desktop/` (Tauri v2 + React 18 + Vite + Zustand + Tailwind)
- **Legacy UI**: `frontend/` (Next.js 16 — no recomendado para nuevo trabajo)
- **RAG**: `rag_pipeline/` (ChromaDB local, ingestión PDF)
- **Guardrails**: `guardrails/validator.py` (validación Pydantic)
- **Model Hub**: `hub_catalog.py` (catálogo GGUF + descargas)
- **MCP Server**: `mcp_server.py` (puerto 8000)

Puertos: backend 7719, MCP 8000.
LLM provider configurable: `llamacpp` (default), `ollama`, `openai`.
Agent harness configurable: `opencode` (default), `native`, `little-coder`, `claude-code`.
Vector DB: `chroma` (default), `supabase`.

---

## Comandos de validación

```bash
# Python — sintaxis
python -m py_compile agent_server.py
python -m py_compile <archivo>

# TypeScript — desktop
npx tsc --noEmit --project desktop/tsconfig.json

# TypeScript — frontend (legacy)
npx tsc --noEmit --project frontend/tsconfig.json

# Lint Python
ruff check agent_server.py config.py hub_catalog.py mcp_server.py

# Build desktop
cd desktop && npm run build

# Build Tauri
cd desktop && npm run tauri build
```

---

## Estructura de archivos clave

- `config.py` — todas las vars de entorno con defaults y validación
- `.env.example` — referencias de vars de entorno (no commitear `.env`)
- `desktop/src/lib/types.ts` — interfaces TypeScript (AgentStep, Behavior, Folder, etc.)
- `desktop/src/lib/store.ts` — Zustand store global
- `desktop/src/lib/api.ts` — capa API (fetch + streamChat)
- `data/` — archivos de datos (router, métricas, telemetría, memoria, runs, snapshots, folders)
- `rag_storage/` — base de vectores ChromaDB

---

## Reglas de trabajo

### Documentación principal

Si existe `project_documentation.md`, usarlo como memoria técnica.
- Leer antes de cambios no triviales.
- Actualizar después de cambios en lógica, arquitectura, estructura, comandos, dependencias, configuración, endpoints, modelos, flujos, comportamiento o decisiones técnicas.
- No actualizar por cambios triviales.
- Conservar información válida previa. Marcar decisiones obsoletas como reemplazadas.

### Selección automática de skills

Cuando el pedido coincida con una intención conocida, elegir automáticamente la skill adecuada:

| Intento del usuario | Skill |
|---|---|
| "documentá el código", "agregá docstrings" | `doc-functions` |
| "refactorizá", "limpiá este módulo" | `block-refactor` |
| "entendé el proyecto", "mapa del código" | `codebase-map` |
| "actualizá la documentación" | `update-project-docs` |
| "continuá", "dejá contexto para seguir" | `handoff-summary` |

### Trabajo por bloques

Para archivos grandes (`agent_server.py` tiene ~7200 líneas):
- No reescribir archivos >400 líneas de una vez.
- Editar por bloques de 200-400 líneas.
- No pegar archivos completos en el chat.
- No repetir análisis ya hecho.

### Operaciones con Markdown

- Antes de editar `.md`, leer su contenido actual.
- Resumir brevemente después de crear/editar/borrar `.md`.
- No reemplazar documentación completa salvo pedido explícito.

### Seguridad

- No commitear `.env`, tokens, claves.
- No exponer secretos en logs o código.
- No borrar archivos sin explicar motivo.
- No ejecutar comandos destructivos sin aprobación.
- No instalar dependencias sin explicar por qué son necesarias.

---

## Skills locales

Disponibles bajo `.opencode/skills/`:
- `codebase-map` — análisis y mapa de la codebase
- `doc-functions` — documentación de funciones/clases
- `block-refactor` — refactors por bloques
- `update-project-docs` — actualización de documentación del proyecto
- `handoff-summary` — resumen para continuar después

---

## Referencias

- `docs/ARCHITECTURE.md` — arquitectura actual
- `docs/API.md` — referencia de API del backend
- `docs/adr/` — registros de decisiones de arquitectura
- `docs/decisions.md` — decisiones técnicas (crear si no existe)
- `docs/flows.md` — flujos de usuario y sistema (crear si no existe)
- `docs/code_map.md` — mapa de código (crear si no existe)
- `project_documentation.md` — memoria técnica principal (crear si no existe)
