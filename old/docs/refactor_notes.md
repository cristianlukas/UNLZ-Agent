# Refactor Notes — UNLZ Agent

> Análisis de riesgo y oportunidades de refactorización.

## Archivos de alto riesgo

### agent_server.py (~7200 líneas)
- **Riesgo**: CRITICO. Archivo monolítico con múltiples responsabilidades
- **Problemas**:
  - Dificultad de navegar y modificar sin riesgo de romper algo
  - Mezcla endpoints, lógica de negocio, tool-calling, config, hub, dev tools
  - Sin tests automatizados
- **Oportunidad**: Separar en módulos:
  - server/endpoints.py (todos los @app.get/@app.post)
  - server/agent_loop.py (tool-calling loop, harnesses, modes)
  - server/llamacpp.py (subprocess management)
  - server/hub.py (model catalog, downloads)
  - server/dev.py (logs, traces)
  - server/knowledge.py (RAG, folders)
  - server/router.py (model routing)
  - server/advanced.py (gated features)
- **Prioridad**: Alta, pero requiere testing antes de tocar

### hub_catalog.py (~670 líneas)
- **Riesgo**: MEDIO. Catálogo estático con datos curados
- **Problemas**:
  - MODELS_CATALOG es una lista enorme inline
  - Requiere actualización manual periódica
  - hardware_profiler depende de psutil (Windows-only con ciertas APIs)
- **Oportunidad**: Externalizar catálogo a JSON externo, cargar dinámicamente
- **Prioridad**: Media

### mcp_server.py
- **Riesgo**: BAJO. Archivo relativamente independiente
- **Problemas**:
  - Conecta al mismo LLM que agent_server.py (duplicación de config)
  - Podría compartir config.py con el backend
- **Oportunidad**: Extraer herramientas comunes a un módulo compartido
- **Prioridad**: Baja

## Archivos de bajo riesgo

### config.py
- Riesgo bajo, bien estructurado
- Funciona como única fuente de verdad para env vars
- No requiere cambios estructurales

### rag_pipeline/ (3 archivos)
- Riesgo bajo, bien separados por responsabilidad
- factory.py, ingest.py, retriever.py tienen responsabilidades claras
- No requieren refactor

### guardrails/validator.py
- Riesgo bajo, archivo pequeño
- Validaciones Pydantic bien definidas
- No requiere cambios

### desktop/ (Tauri + React)
- Riesgo bajo-medio
- App.tsx tiene múltiples responsabilidades (health polling, routing, sidebar)
- store.ts bien separado con Zustand
- api.ts tiene todas las funciones API en un archivo (~828 líneas)
- Oportunidad: dividir api.ts en módulos por dominio (chat, hub, knowledge, etc.)
- Prioridad: Baja-Media

### frontend/ (Next.js legacy)
- Riesgo bajo (no se recomienda tocar)
- Marcado como legacy, no activo

## Oportunidades de mejora general

### Testing
- No hay tests automatizados
- Prioridad alta: al menos tests de config.py y guardrails/validator.py
- Luego tests de endpoints críticos

### Documentación inline
- agent_server.py tiene muy poca documentación inline
- Funciones grandes sin docstrings
- Oportunidad: agregar docstrings por bloques (skill: doc-functions)

### Typing
- config.py y guardrails/validator.py tienen typing
- agent_server.py tiene typing parcial
- Oportunidad: agregar types a funciones principales

### Performance
- ChromaDB en rag_storage/ puede crecer sin límite
- Oportunidad: agregar política de limpieza de vectores
- Oportunidad: agregar streaming de logs en lugar de tail completo

### Seguridad
- No hay autenticación en el backend
- Diseñado para uso local, acceptable
- .env excluido de git, correcto
- No se exponen secretos en logs, correcto
ENDOFFILE
