# handoff-summary Skill

> Prepara resumen compacto para continuar trabajo despues de una pausa.

## Cuándo usar

Cuando el usuario pide:
- "seguí"
- "continuá"
- "retomá desde donde quedó"
- "resumí el estado"
- "prepará handoff"
- "dejá contexto para seguir despues"

## Workflow

1. Identificar la tarea en curso o ultima tarea completada
2. Revisar archivos modificados recientemente
3. Crear resumen compacto con:
   - Objetivo actual
   - Archivos tocados (con lineas relevantes)
   - Decisiones tomadas
   - Bloques completados vs pendientes
   - Proximo paso exacto
   - Riesgos o bloqueantes conocidos
4. Guardar resumen en archivo temporal si la tarea es larga
5. No repetir todo el historial

## Formato del resumen

Handoff: [titulo breve]
Objetivo: [que se esta haciendo]
Estado: [en progreso | pausado | completado]
Archivos tocados:
- archivo.py:linea_X - cambio realizado / pendiente
Decisiones:
- [decision tomada] -> [razon]
Pendiente:
- [proximo paso exacto]
Riesgos:
- [si aplica]

## Reglas

- No repetir todo el historial de la conversacion
- Ser especifico con lineas y archivos
- Incluir el proximo paso exacto para poder retomar
- No incluir informacion irrelevante
- Mantener el resumen compacto (<50 lineas)
- Si no hay tarea en curso, resumir el estado actual del proyecto
