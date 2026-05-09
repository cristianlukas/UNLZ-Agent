# Decisions — UNLZ Agent

> Registro de decisiones técnicas relevantes.

## D001 — Desktop recomendado sobre Legacy Frontend
- **Fecha**: 2026-04-27
- **Contexto**: El proyecto tiene dos UIs: desktop/ (Tauri+React) y frontend/ (Next.js)
- **Decisión**: Nuevo trabajo debe ir en desktop/. frontend/ marcado como legacy.
- **Razón**: Tauri ofrece menor footprint, acceso nativo a filesystem, mejor integración con sistema. Next.js legacy usa arquitectura diferente y no se mantiene activamente.
- **Estado**: Activa

## D002 — Backend en archivo único
- **Fecha**: 2026-04-27
- **Contexto**: agent_server.py tiene ~7200 líneas en un solo archivo
- **Decisión**: Mantener monolito por ahora, refactorizar cuando sea necesario
- **Razón**: El archivo funciona bien para el tamaño actual. Separarlo prematuramente agregaría complejidad de imports y deployment. Se recomienda refactorizar por bloques cuando supere 10000 líneas o múltiples responsabilidades claramente separables.
- **Estado**: Activa

## D003 — LLM Provider por defecto: llamacpp
- **Fecha**: 2026-04-27
- **Contexto**: config.py tiene LLM_PROVIDER con default llamacpp
- **Decisión**: Mantener llamacpp como default, soportar ollama y openai como alternativas
- **Razón**: llama.cpp permite ejecutar modelos locales sin servidor externo. Ollama requiere proceso separado. OpenAI requiere conexión cloud.
- **Estado**: Activa

## D004 — Vector DB por defecto: ChromaDB local
- **Fecha**: 2026-04-27
- **Contexto**: config.py tiene VECTOR_DB con default chroma
- **Decisión**: Mantener ChromaDB local como default, soportar Supabase como alternativa cloud
- **Razón**: ChromaDB funciona 100% offline, ideal para asistente local. Supabase requiere infraestructura cloud.
- **Estado**: Activa

## D005 — Advanced Mode gated
- **Fecha**: 2026-04-27
- **Contexto**: Se añadieron 6 feature groups avanzados (profiles, benchmarks, presets, hardware detection, launch history, health monitoring)
- **Decisión**: Todos los features avanzados requieren UNLZ_ADVANCED_MODE=1 en .env
- **Razón**: Estos features agregan complejidad y endpoints adicionales que no son necesarios para uso básico. El flag permite activarlos solo cuando se necesitan.
- **Estado**: Activa

## D006 — Data files en directorio data/
- **Fecha**: 2026-04-27
- **Contexto**: Configuración, métricas, memoria, runs, snapshots, folders
- **Decisión**: Todos los datos persistentes en data/, excluidos de git via .gitignore
- **Razón**: Los datos son específicos de cada instalación y pueden contener información sensible. .gitignore excluye data/ y rag_storage/.
- **Estado**: Activa

## D007 — Agent Harness configurables
- **Fecha**: 2026-04-27
- **Contexto**: Diferentes estrategias de tool-calling y planning
- **Decisión**: Soportar 4 harnesses: opencode (default), native, little-coder, claude-code
- **Razón**: Diferentes tareas requieren diferentes estrategias. opencode ofrece el mejor balance. native es más simple. little-coder para tareas de código. claude-code para compatibilidad con flujo Claude Code.
- **Estado**: Activa

## D008 — Chat modes separados
- **Fecha**: 2026-04-27
- **Contexto**: Diferentes modos de interacción con el agente
- **Decisión**: 4 modes: normal (default), plan, iterate, simple
- **Razón**: normal para uso general. plan para tareas complejas con planning explícito. iterate para tareas con feedback. simple para preguntas directas sin tool-calling.
- **Estado**: Activa

## D009 — MCP Server como proceso separado
- **Fecha**: 2026-04-27
- **Contexto**: Integración con herramientas externas via MCP
- **Decisión**: mcp_server.py corre en puerto 8000 como proceso independiente
- **Razón**: Separar MCP del backend principal (7719) permite que agentes externos consuman las herramientas sin depender del ciclo de vida del servidor de chat.
- **Estado**: Activa

## D010 — Guardrails con validación Pydantic
- **Fecha**: 2026-04-27
- **Contexto**: Validación de input/output del agente
- **Decisión**: Guardrails usa modelos Pydantic para validar entradas y salidas
- **Razón**: Pydantic ofrece validación tipada eficiente. Detecta patrones prohibidos y contenido inseguro. Se ejecuta inline en el tool-calling loop.
- **Estado**: Activa
ENDOFFILE
