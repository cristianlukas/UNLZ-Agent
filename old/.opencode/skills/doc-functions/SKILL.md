# doc-functions Skill

> Documenta funciones y clases con docstrings.

## Cuándo usar

Cuando el usuario pide:
- "documentá el código"
- "agregá docstrings"
- "comentá funciones"
- "explicá el codigo en el mismo archivo"
- "mejorá la documentación interna"

## Workflow

1. Leer project_documentation.md para contexto
2. Identificar archivos a documentar
3. Para archivos >400 lineas, trabajar por bloques de 200-400 lineas
4. Para cada archivo:
   a. Leer el bloque a documentar
   b. Identificar funciones y clases que necesitan docstrings
   c. Agregar docstrings con: descripcion, params, returns, exceptions
   d. Agregar comentarios solo donde la logica no sea obvia
5. Validar sintaxis: python -m py_compile <archivo>
6. Continuar con el siguiente bloque

## Reglas

- No reescribir archivos grandes completos de una sola vez
- No pegar archivos completos en el chat
- No comentar linea por linea
- No comentar imports obvios
- No cambiar logica, nombres, formato ni comportamiento
- Preferir docstrings sobre comentarios inline
- Formato docstring: Google style (descripcion, Args:, Returns:, Raises:)
- Validar sintaxis al final de cada bloque
- No documentar getters/setters triviales
- Documentar funciones publicas (no privadas, que empiezan con _)
- Para funciones muy largas (>100 lineas), agregar resumen inline ademas del docstring

## Ejemplo

async def chat(req: ChatRequest) -> StreamingResponse:
    Docstring principal. Tool-calling loop con SSE streaming.
    Args: req - Request con message, history, mode.
    Returns: StreamingResponse con eventos SSE.
