# update-project-docs Skill

> Actualiza la documentación del proyecto.

## Cuándo usar

Cuando el usuario pide:
- "actualizá la documentación"
- "actualizá los .md"
- "documentá los flujos"
- "actualizá project_documentation.md"
- "dejá asentado cómo funciona"

## Workflow

1. Leer project_documentation.md actual
2. Leer docs existentes (ARCHITECTURE.md, API.md, code_map.md, decisions.md, flows.md, refactor_notes.md)
3. Identificar qué cambió desde la última actualización
4. Actualizar solo las secciones afectadas:
   - project_documentation.md: cambios en lógica, arquitectura, estructura, comandos, dependencias, configuración, endpoints, modelos, flujos, comportamiento, decisiones técnicas
   - docs/code_map.md: nuevos archivos, cambios de responsabilidad
   - docs/architecture.md: cambios arquitecturales
   - docs/flows.md: nuevos flujos o cambios en existentes
   - docs/decisions.md: nuevas decisiones técnicas
   - docs/refactor_notes.md: nuevos riesgos u oportunidades
5. Conservar información válida previa
6. Marcar decisiones obsoletas como reemplazadas o históricas
7. Resumir brevemente qué se modificó y por qué

## Reglas

- No duplicar documentación
- No crear documentación duplicada si ya existe una fuente clara de verdad
- Conservar información previa que siga siendo válida
- Marcar decisiones obsoletas como reemplazadas, corregidas o históricas
- No actualizar por cambios triviales
- No reemplazar documentación completa salvo pedido explícito
- Antes de editar cualquier .md, leer su contenido actual
- Usar formato consistente con documentación existente

## Qué NO actualizar

- Cambios triviales (nombres de variables, formato de código)
- Comentarios inline de código
- Mensajes de log
- Cambios en dependencias de desarrollo (devDependencies)
- Configuración de build que no afecta al usuario

## Qué SÍ actualizar

- Nuevos endpoints de API
- Nuevas funciones o clases importantes
- Cambios en la arquitectura
- Nuevos flujos de usuario
- Cambios en comandos de ejecución
- Nuevas dependencias
- Cambios en configuración (vars de entorno)
- Decisiones técnicas nuevas
- Cambios en estructura de archivos
