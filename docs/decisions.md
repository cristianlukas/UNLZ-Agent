# Decisions — UNLZ Agent

> Registro de decisiones técnicas relevantes. Última actualización: 2026-05-02.

## D001 — Opencode-only architecture
- **Fecha**: 2026-05-02
- **Contexto**: El proyecto tenía multi-provider (ollama, llamacpp, openai) y multi-harness (native, little-coder, claude-code, opencode)
- **Decisión**: Simplificar a opencode-only con llamacpp como backend
- **Razón**: Reducir complejidad, mantener un solo flujo de ejecución verificable, eliminar deuda técnica de múltiples paths
- **Impacto**: agent_server.py reducido de ~8765 a ~2154 líneas, config.py simplificado, desktop views reducidas
- **Estado**: Activa

## D002 — Bootstrap automático de runtime
- **Fecha**: 2026-05-02
- **Contexto**: El usuario debía configurar manualmente llama.cpp, modelo, y opencode
- **Decisión**: Auto-detectar hardware, seleccionar modelo por bucket VRAM, descargar desde HuggingFace, generar config opencode
- **Razón**: Mejorar experiencia de primer uso, reducir fricción de configuración
- **Estado**: Activa

## D003 — Home directory aislado para opencode
- **Fecha**: 2026-05-02
- **Contexto**: opencode usaba el home del usuario, lo que podía interferir con config global
- **Decisión**: Forzar HOME, USERPROFILE, XDG_CONFIG_HOME a `data/.unlz_internal/opencode_home/`
- **Razón**: Aislar config de opencode del usuario, evitar conflictos con instalación global
- **Estado**: Activa

## D004 — Error explanation para humanos
- **Fecha**: 2026-05-02
- **Contexto**: Los errores técnicos de opencode/llama.cpp eran ilegibles para usuarios no técnicos
- **Decisión**: `explain_error_for_humans()` traduce errores a mensajes con causas comunes y pasos de fix
- **Razón**: Mejorar experiencia de usuario, especialmente en modo newbie
- **Estado**: Activa

## D005 — Newbie UX con onboarding
- **Fecha**: 2026-05-02
- **Contexto**: El proyecto no tenía sistema de onboarding ni perfil de usuario
- **Decisión**: Modal de onboarding con checks de salud, perfil de usuario (experience_level, detail_level, language), task templates
- **Razón**: Guiar al usuario en primer uso, inyectar hints de perfil en prompts para adaptaciones
- **Estado**: Activa

## D006 — Desktop recomendado sobre Legacy Frontend
- **Fecha**: 2026-04-27
- **Contexto**: El proyecto tiene dos UIs: desktop/ (Tauri+React) y frontend/ (Next.js)
- **Decisión**: Nuevo trabajo debe ir en desktop/. frontend/ marcado como legacy.
- **Razón**: Tauri ofrece menor footprint, acceso nativo a filesystem, mejor integración con sistema
- **Estado**: Activa

## D007 — Backend en archivo único
- **Fecha**: 2026-04-27
- **Contexto**: agent_server.py tenía ~8765 líneas, ahora ~2154 tras refactor a opencode-only
- **Decisión**: Mantener monolito por ahora. Tamaño actual manejable
- **Razón**: El archivo funciona bien para ~2154 líneas. Separarlo prematuramente agregaría complejidad
- **Estado**: Activa

## D008 — Desktop recomendado sobre Legacy Frontend
- **Fecha**: 2026-04-27
- **Contexto**: El proyecto tiene dos UIs: desktop/ (Tauri+React) y frontend/ (Next.js)
- **Decisión**: Nuevo trabajo debe ir en desktop/. frontend/ marcado como legacy.
- **Razón**: Tauri ofrece menor footprint, acceso nativo a filesystem, mejor integración con sistema
- **Estado**: Activa

## D009 — Data files en directorio data/
- **Fecha**: 2026-04-27
- **Contexto**: Configuración, métricas, memoria, runs, snapshots
- **Decisión**: Todos los datos persistentes en data/, excluidos de git via .gitignore
- **Razón**: Los datos son específicos de cada instalación y pueden contener información sensible
- **Estado**: Activa

## D010 — Config keys bloqueadas
- **Fecha**: 2026-05-02
- **Contexto**: El usuario podía modificar cualquier variable de settings
- **Decisión**: `_LOCKED_ENV_KEYS` bloquea: AGENT_HARNESS, AGENT_EXECUTION_MODE, LLM_PROVIDER, LLAMACPP_EXECUTABLE, LLAMACPP_MODEL_PATH, LLAMACPP_MODEL_ALIAS
- **Razón**: Prevenir que el usuario rompa la configuración crítica del runtime
- **Estado**: Activa

## D011 — Features removidas
- **Fecha**: 2026-05-02
- **Contexto**: Versión anterior tenía: multi-provider, multi-harness, task router, model hub, RAG pipeline, advanced mode, plan/iterate modes
- **Decisión**: Remover todas estas features para simplificar
- **Razón**: Reducir complejidad, mantener foco en opencode + llama.cpp, eliminar deuda técnica
- **Estado**: Histórica (features removidas)
