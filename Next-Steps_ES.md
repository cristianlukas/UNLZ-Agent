# Próximos Pasos y Hoja de Ruta

[🇬🇧 English](Next-Steps.md) | [🇪🇸 Español](Next-Steps_ES.md)

Ahora que la estructura principal está en su lugar, sigue esta hoja de ruta para finalizar el proyecto para tu portafolio.

## Fase 1: Integración (Puesta en Marcha)

- [ ] **Instalar Dependencias en Máquina Local**
      Ejecuta `pip install -r requirements.txt` en este directorio.

- [ ] **Configurar Ollama**
  - Instala Ollama.
  - Ejecuta `ollama pull qwen2.5-coder:14b`.
  - Asegúrate de que escuche en el puerto 11434.

- [ ] **Configurar n8n**
  - Importa `n8n_workflow.json` en tu instancia local de n8n.
  - Configura las Credenciales de Ollama (URL Base: `http://localhost:11434` o `http://host.docker.internal:11434`).
  - Configura las credenciales de Supabase en n8n.

- [ ] **Probar el Ciclo**
  - Dispara el flujo de trabajo de n8n manualmente.
  - Verifica que llame correctamente a la herramienta `get_system_stats` desde tu `mcp_server.py` en ejecución.

## Fase 2: Mejoras Técnicas (Las Características "Senior")

- [ ] **Monitoreo Real de GPU**
      Actualmente `mcp_server.py` usa datos simulados para `gpu_stats`.
  - **Acción**: Modificar `get_system_stats` para usar `shutil.which('nvidia-smi')` y ejecutar el comando para obtener el uso real de VRAM.
  - _Por qué_: Demuestra que puedes manejar interoperabilidad de hardware real.

- [ ] **Implementar Almacenamiento Vectorial (RAG)**
  - **Acción**: Crear un script Python (o flujo n8n) que:
    1. Lea PDFs de `UNLZ-AI-STUDIO/system/data`.
    2. Los divida en fragmentos (chunking).
    3. Genere embeddings (usa Qwen o un modelo pequeño de embeddings).
    4. Los inserte (upsert) en la tabla `vector` de Supabase.
  - _Por qué_: Esencial para la parte de "Investigación" del agente.

- [ ] **Agregar Herramienta de "Búsqueda"**
  - **Acción**: Agregar una nueva herramienta a `mcp_server.py` llamada `search_local_files(query: str)`.
  - Debería filtrar la lista de archivos o hacer grep en los contenidos para encontrar archivos relevantes antes de leerlos.

## Fase 3: Pulido del Portafolio (La Presentación)

- [ ] **Grabar un Video Demo**
  - Graba la pantalla con un flujo completo:
    1. Tú preguntando: "¿Cómo está la carga del servidor?" -> El Agente consulta MCP -> Devuelve estadísticas reales.
    2. Tú preguntando: "Resume la investigación sobre X" -> El Agente consulta Supabase -> Devuelve la respuesta.
  - Sube a YouTube/Loom e incrústalo en `README_ES.md`.

- [ ] **Subir a GitHub**
  - `git push origin master`
