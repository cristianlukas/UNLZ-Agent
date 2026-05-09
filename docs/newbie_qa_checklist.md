# QA Checklist — Newbie Friendly

## Precondiciones
- Backend corriendo en `127.0.0.1:7719`
- Desktop app abierta
- Sin estado previo de onboarding (`onboardingCompleted=false` en store)

## 1. Onboarding inicial
1. Abrir la app por primera vez.
2. Verificar que aparece el modal de onboarding.
3. Confirmar que lista checks de provider, puertos, data y RAG.
4. Si hay warnings/errors, presionar `Dejar todo listo`.
5. Verificar respuesta `status=ok` y posibilidad de continuar.

Criterio de aceptación:
- El modal no bloquea permanentemente cuando el sistema queda en estado usable.

## 2. Modo Simple por defecto
1. Ir a Configuración.
2. Verificar que `Modo de interfaz` está en `Simple (recomendado)`.
3. Volver al chat y comprobar que no se muestran controles avanzados (plan/agent mode/tools mode/exec mode).

Criterio de aceptación:
- La UI expone solo controles esenciales en simple.

## 3. Plantillas de tareas
1. En chat nuevo, verificar botones de plantillas visibles.
2. Click en cada plantilla y validar que precarga texto en input.
3. Enviar una plantilla y confirmar ejecución normal del flujo.

Criterio de aceptación:
- Las 4 plantillas iniciales se cargan desde backend y son usables.

## 4. Timeline en tiempo real
1. Enviar una tarea de código que tome algunos segundos.
2. Verificar cambios de estado (analizando/leyendo/aplicando/generando/finalizado).

Criterio de aceptación:
- El timeline no queda congelado y termina en `Finalizado`.

## 5. Errores accionables
1. Forzar error (por ejemplo, provider no disponible).
2. Verificar que el mensaje incluye:
- Qué pasó
- Posibles causas
- Cómo resolverlo

Criterio de aceptación:
- El usuario recibe pasos concretos, no solo traza técnica.

## 6. Centro de salud
1. Ir a Configuración, sección `Estado del agente`.
2. Validar provider/version, modelo y estado RAG.

Criterio de aceptación:
- Datos visibles y coherentes con backend.

## 7. APIs nuevas (smoke)
Validar respuestas HTTP 200 para:
- `GET /health/onboarding`
- `POST /health/onboarding/fix`
- `GET /newbie/task-templates`
- `GET /newbie/profile`
- `POST /newbie/profile`
- `GET /health/center`

Criterio de aceptación:
- Todas responden con JSON válido y shape esperado.
