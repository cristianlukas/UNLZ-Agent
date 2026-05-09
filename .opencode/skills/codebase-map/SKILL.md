# codebase-map Skill

> Analiza y mapea la codebase de UNLZ Agent.

## Cuándo usar

Cuando el usuario pide:
- "entendé el proyecto"
- "analizá la app"
- "hacé un mapa del código"
- "explicame la arquitectura"
- "prepará contexto"
- "quiero que conozcas la codebase"

## Workflow

1. Leer project_documentation.md para contexto previo
2. Explorar estructura de archivos con Glob
3. Inspeccionar archivos clave:
   - agent_server.py (por secciones de 400 líneas)
   - config.py
   - hub_catalog.py
   - mcp_server.py
   - desktop/src/App.tsx
   - desktop/src/lib/store.ts
   - desktop/src/lib/api.ts
   - desktop/src/lib/types.ts
   - rag_pipeline/ (factory.py, ingest.py, retriever.py)
   - guardrails/validator.py
4. Actualizar docs/code_map.md con hallazgos
5. No modificar código fuente
6. Resumir responsabilidades por archivo, clase y módulo

## Reglas

- No leer archivos enormes completos si puede inspeccionarse por secciones
- No modificar código fuente
- Conservar información válida previa en code_map.md
- Marcar como inferido lo que no se puede verificar directamente
- Actualizar solo si hay cambios relevantes detectados

## Archivos de referencia

- AGENTS.md — reglas generales del agente
- project_documentation.md — memoria técnica
- docs/ARCHITECTURE.md — arquitectura del sistema (existente)
- docs/API.md — referencia de API (existente)
- docs/adr/ — decisiones de arquitectura (existente)
