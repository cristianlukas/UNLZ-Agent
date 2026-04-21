# Proximos Pasos y Hoja de Ruta

[🇬🇧 English](Next-Steps.md) | [🇪🇸 Español](Next-Steps_ES.md)

Esta hoja de ruta se enfoca en fortalecer **UNLZ Agent** como plataforma de agente (planificación, ejecución, validación, memoria y ecosistema MCP), más allá del modelo usado.

## Fase 1: Núcleo del Agente (Planificación + Ejecución)

- [ ] Implementar loop explícito planner/executor/critic en backend (`plan -> ejecutar -> validar -> reintentar`), no sólo por prompt.
- [ ] Soportar grafo de tareas (pasos dependientes, pasos paralelizables, checkpoints).
- [ ] Agregar controles de iteración: máximo de iteraciones, máximo de tool calls, límite de tiempo global y por paso.
- [ ] Persistir trazas de ejecución por corrida (versiones del plan, tools usadas, salidas, veredicto final).

## Fase 2: Confiabilidad y Seguridad de Herramientas

- [ ] Estandarizar contratos de tools: esquemas tipados de entrada/salida, códigos de error y hints de retry.
- [ ] Agregar claves de idempotencia para tools mutantes (`run_windows_command`, escritura de archivos).
- [ ] Implementar motor de políticas por contexto (allow/confirm/deny) según tipo de operación (filesystem/red/procesos/sistema).
- [ ] Agregar modo dry-run para tareas accionables antes de ejecutar cambios reales.

## Fase 3: Verificación y Autocorrección

- [ ] Agregar primitivas post-acción de verificación (archivo existe, contenido cambió, validación de salida de comando).
- [ ] Definir estrategias automáticas de fallback cuando falla una tool (comando/proveedor alternativo).
- [ ] Puntuar confianza por respuesta y por acción ejecutada.
- [ ] Detectar afirmaciones no verificadas en modo investigación y forzar citas cuando la confianza sea baja.

## Fase 4: MCP e Integraciones

- [ ] Separar capacidades MCP por servidores de dominio (filesystem, shell, browser, docs, repo) con scopes explícitos.
- [ ] Agregar perfiles de permisos por servidor y auditoría visible de scopes.
- [ ] Incorporar tablero de salud de conectores (latencia, tasa de error, cuota).
- [ ] Agregar proveedores web-search pluggables con fusión de ranking (Google/DDG/SerpAPI/Bing).

## Fase 5: Memoria e Ingeniería de Contexto

- [ ] Implementar memoria de largo horizonte con estrategia de decaimiento y recuperación (reciente, semántica, ligada a tarea).
- [ ] Separar memoria por carpeta y por conversación.
- [ ] Agregar compresión automática de contexto (resúmenes + facts críticos fijados).
- [ ] Agregar snapshots de estado para retomar tareas multi-sesión.

## Fase 6: UX Competitiva (estilo Codex/Claude)

- [ ] UI de “Plan Review” con alternativas, tradeoffs, camino elegido y puerta explícita de aprobación.
- [ ] “Execution Console” con timeline de pasos y estado en vivo.
- [ ] Controles de “reintentar desde este paso” y “ramificar desde aquí”.
- [ ] Suite de benchmarks: tasa de éxito, tiempo a completar, cantidad de correcciones, eficiencia token/tool.

## Fase 7: Producción y Escalabilidad

- [ ] Quality gates en CI: tests backend/frontend y smoke tests empaquetados.
- [ ] Firma de artefactos y metadata de build reproducible.
- [ ] Telemetría estructurada (opt-in) para métricas de calidad del agente.
- [ ] Publicar ADRs (Architecture Decision Records) para decisiones clave de agente/MCP.
