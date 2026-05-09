# block-refactor Skill

> Refactoriza código por bloques pequeños y seguros.

## Cuándo usar

Cuando el usuario pide:
- "refactorizá este módulo"
- "mejorá la estructura"
- "ordená el código"
- "separá responsabilidades"
- "limpiá este archivo"
- "simplificá la app"
- "modularizá"
- "hacé más mantenible"

## Workflow

1. Leer project_documentation.md para contexto
2. Identificar el alcance del refactor
3. Dividir el trabajo en bloques de 200-400 líneas
4. Para cada bloque:
   a. Leer el bloque actual
   b. Identificar mejoras (extracción de funciones, eliminación de duplicación, claridad)
   c. Aplicar cambios mínimos y verificables
   d. Validar sintaxis: python -m py_compile o npx tsc --noEmit
   e. Marcar bloque completado
5. Continuar con el siguiente bloque
6. Al finalizar, verificar que no se rompió comportamiento

## Reglas

- No mezclar refactor con nuevas funcionalidades salvo pedido explícito
- No reescribir archivos completos de una vez
- Mantener comportamiento existente
- No cambiar nombres de funciones/variables salvo que sea necesario para claridad
- No cambiar signatures de funciones públicas salvo acuerdo explícito
- Validar después de cada bloque
- No hacer commits salvo pedido explícito
- Si el bloque requiere cambios en archivos relacionados, documentarlos y pedir aprobación

## Prioridades de refactor

1. Eliminar código duplicado entre archivos
2. Separar responsabilidades en agent_server.py (múltiples @app decorators mezclados)
3. Extraer helpers repetitivos en funciones reutilizables
4. Mejorar typing donde sea parcial
5. Simplificar condicionales complejos
6. Agregar logging donde falta

## Archivos objetivo prioritarios

- agent_server.py: separar endpoints de lógica de negocio
- hub_catalog.py: externalizar MODELS_CATALOG a JSON
- desktop/src/lib/api.ts: dividir en módulos por dominio
- mcp_server.py: extraer herramientas comunes
