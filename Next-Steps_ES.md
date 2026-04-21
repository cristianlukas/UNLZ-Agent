# Proximos Pasos y Hoja de Ruta

[🇬🇧 English](Next-Steps.md) | [🇪🇸 Español](Next-Steps_ES.md)

Roadmap actualizado al estado actual del proyecto (desktop + agent_server).

## Fase 1: Estabilidad Operativa

- [ ] Agregar tests automatizados para `/chat` (casos `step/chunk/error/done`).
- [ ] Agregar test para fallback de `web_search` (sin resultados y error de proveedor).
- [ ] Registrar metricas basicas (latencia, errores por endpoint, tool failures).
- [ ] Implementar rotacion de `agent_server.log`.

## Fase 2: Agente y Herramientas

- [ ] Mejorar policy de comandos Windows (listas permitidas por contexto + audit trail).
- [ ] Agregar confirmaciones finas por tipo de operacion (filesystem, red, procesos).
- [ ] Incorporar fuentes/citas para respuestas de investigacion cuando usa `web_search`.
- [ ] Añadir soporte de busqueda web adicional configurable (ej. SerpAPI/Bing).

## Fase 3: UX de Chat

- [ ] Mostrar motivo de fallo de herramienta en UI con detalle expandible.
- [ ] Historial de ediciones de mensajes (versionado liviano).
- [ ] Mejoras de accesibilidad (focus states, atajos, lectura de pantalla).

## Fase 4: Distribucion

- [ ] Pipeline CI para build portable (`build-portable.ps1`) con artefactos versionados.
- [ ] Firma de binarios para distribucion Windows.
- [ ] Guia de release reproducible (checklist + versionado semantico).

## Fase 5: Documentacion

- [ ] Mantener docs de API sincronizados por version.
- [ ] Agregar seccion de "breaking changes" entre modo legado y desktop.
- [ ] Publicar un diagrama de secuencia del flujo chat + tools + SSE.
