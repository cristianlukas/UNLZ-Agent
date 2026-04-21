# Proximos Pasos y Hoja de Ruta

[🇬🇧 English](Next-Steps.md) | [🇪🇸 Español](Next-Steps_ES.md)

Esta hoja de ruta se enfoca en fortalecer **UNLZ Agent** como plataforma de agente (planificación, ejecución, validación, memoria y ecosistema MCP), más allá del modelo usado.

## Fase 1: Núcleo del Agente (Planificación + Ejecución)

- [x] Implementar loop explícito planner/executor/critic en backend (`plan -> ejecutar -> validar -> reintentar`), no sólo por prompt.
- [x] Soportar grafo de tareas (pasos dependientes, pasos paralelizables, checkpoints).
- [x] Agregar controles de iteración: máximo de iteraciones, máximo de tool calls, límite de tiempo global y por paso.
- [x] Persistir trazas de ejecución por corrida (versiones del plan, tools usadas, salidas, veredicto final).

## Fase 2: Confiabilidad y Seguridad de Herramientas

- [x] Estandarizar contratos de tools: esquemas tipados de entrada/salida, códigos de error y hints de retry.
- [x] Agregar claves de idempotencia para tools mutantes (`run_windows_command`, escritura de archivos).
- [x] Implementar motor de políticas por contexto (allow/confirm/deny) según tipo de operación (filesystem/red/procesos/sistema).
- [x] Agregar modo dry-run para tareas accionables antes de ejecutar cambios reales.

## Fase 3: Verificación y Autocorrección

- [x] Agregar primitivas post-acción de verificación (archivo existe, contenido cambió, validación de salida de comando).
- [x] Definir estrategias automáticas de fallback cuando falla una tool (comando/proveedor alternativo).
- [x] Puntuar confianza por respuesta y por acción ejecutada.
- [x] Detectar afirmaciones no verificadas en modo investigación y forzar citas cuando la confianza sea baja.

## Fase 4: MCP e Integraciones

- [x] Separar capacidades MCP por servidores de dominio (filesystem, shell, browser, docs, repo) con scopes explícitos.
- [x] Agregar perfiles de permisos por servidor y auditoría visible de scopes.
- [x] Incorporar tablero de salud de conectores (latencia, tasa de error, cuota).
- [x] Agregar proveedores web-search pluggables con fusión de ranking (Google/DDG/SerpAPI/Bing).

## Fase 5: Memoria e Ingeniería de Contexto

- [x] Implementar memoria de largo horizonte con estrategia de decaimiento y recuperación (reciente, semántica, ligada a tarea).
- [x] Separar memoria por carpeta y por conversación.
- [x] Agregar compresión automática de contexto (resúmenes + facts críticos fijados).
- [x] Agregar snapshots de estado para retomar tareas multi-sesión.

## Fase 6: UX Competitiva (estilo Codex/Claude)

- [x] UI de “Plan Review” con alternativas, tradeoffs, camino elegido y puerta explícita de aprobación.
- [x] “Execution Console” con timeline de pasos y estado en vivo.
- [x] Controles de “reintentar desde este paso” y “ramificar desde aquí”.
- [x] Suite de benchmarks: tasa de éxito, tiempo a completar, cantidad de correcciones, eficiencia token/tool.

## Fase 7: Producción y Escalabilidad

- [x] Quality gates en CI: tests backend/frontend y smoke tests empaquetados.
- [x] Firma de artefactos y metadata de build reproducible.
- [x] Telemetría estructurada (opt-in) para métricas de calidad del agente.
- [x] Publicar ADRs (Architecture Decision Records) para decisiones clave de agente/MCP.

