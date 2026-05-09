# Flows — UNLZ Agent

> Flujos de usuario y del sistema.

## Flujo: Chat con streaming

1. Usuario escribe mensaje en Desktop UI (ChatView)
2. App.tsx envía POST /chat a agent_server.py (puerto 7719)
   - Body: { message, history, system_prompt, mode, conversation_id, ... }
3. agent_server.py:
   a. Lee config.py para determinar LLM provider y modelo
   b. Si llamacpp y no running -> llamacpp_start()
   c. Construye contexto: historial + RAG retrieval (si habilitado)
   d. Ejecuta tool-calling loop con LangChain
   e. Si mode=plan: genera plan, ejecuta pasos, valida resultados
   f. Si mode=iterate: iteración guiada con feedback
   g. Aplica guardrails a output
4. Responde con SSE events:
   - run: inicia corrida con run_id
   - step: tool call o acción del agente
   - chunk: fragmento de respuesta textual
   - confidence: score de confianza + tool calls usados
   - error: error en ejecución
   - done: corrida completada
5. Desktop UI streamChat() recibe events y:
   - Actualiza Zustand store (messages)
   - StreamingRenderer renderiza en tiempo real
   - ChatView muestra typing indicator

## Flujo: Gestión de conversaciones

1. Crear: POST /conversations -> retorna conversation_id
2. Listar: GET /conversations -> array de Conversacion
3. Seleccionar: GET /conversations/{id} -> conversation + messages
4. Eliminar: DELETE /conversations/{id}
5. Snapshot: GET/POST /snapshots/{id} -> guarda/restaura estado completo
6. Cada mensaje se persiste en data/snapshots/{conversation_id}.json

## Flujo: Ingestión RAG

1. Usuario selecciona PDFs en KnowledgeView
2. POST /knowledge/ingest con files
3. agent_server.py:
   a. Guarda files en directorio de conocimiento
   b. rag_pipeline/ingest.py:
      - PyPDFLoader carga contenido
      - RecursiveCharacterTextSplitter divide en chunks (1000 chars, 200 overlap)
      - get_embeddings() obtiene provider (chroma/supabase)
      - Vector store hace upsert de chunks
4. Responde con lista de documentos ingested
5. En próximos chats, retriever busca similitud y inyecta contexto

## Flujo: Model Hub

1. GET /hub/catalog -> retorna MODELS_CATALOG de hub_catalog.py
2. GET /hub/search?q=llama -> filtra catálogo por query
3. Usuario selecciona modelo -> POST /hub/start-download
   - Body: { model_id }
4. agent_server.py:
   a. Descarga desde HuggingFace usando HF API
   b. Guarda en directorio de modelos
   c. Retorna download_id para tracking
5. GET /hub/download-progress/{download_id} -> porcentaje y estado
6. POST /hub/apply-model -> actualiza .env con nuevo modelo
7. Hardware profiler filtra recomendaciones según GPU/VRAM/RAM

## Flujo: Behaviors

1. GET /behaviors -> lista de behaviors locales
2. POST /behaviors -> crea behavior nuevo con system prompt
3. PUT /behaviors/{id} -> actualiza behavior
4. DELETE /behaviors/{id} -> elimina behavior
5. Behaviors se almacenan en data/local_behaviors.json
6. Se pueden asignar a conversaciones o carpetas específicas

## Flujo: Folders

1. GET /folders -> lista de carpetas
2. POST /folders -> crea carpeta con nombre y descripción
3. PUT /folders/{id} -> actualiza carpeta
4. DELETE /folders/{id} -> elimina carpeta
5. Cada folder tiene: id, name, description, created_at, files[]
6. Las conversaciones pueden asociarse a un folder (folder_id en chat request)
7. Memoria RAG se separa por folder

## Flujo: Model Routing

1. GET /router/config -> retorna task_router.json
2. UI muestra heatmap: areas vs modelos con accuracy/latency
3. POST /router/config -> actualiza mapeo area->modelo
4. POST /router/recalibrate -> recalibra con métricas acumuladas
5. router_metrics.jsonl registra: timestamp, area, model, accuracy, latency, success
6. El router selecciona automáticamente el mejor modelo según el área de la consulta

## Flujo: Harnesses

1. GET /harnesses/status -> lista de harnesses disponibles
2. POST /harnesses/install -> instala un harness
3. Cada harness define:
   - Tool-calling strategy
   - Planning approach
   - Error handling
   - Response format
4. Se selecciona con AGENT_HARNESS en .env o harness_override en chat request

## Flujo: Health & Monitoring

1. GET /health -> status global + por componente (llm, rag, knowledge)
2. GET /health/connectors -> health de cada connector (latencia, error rate, quota)
3. GET /health/stats -> system stats (CPU, RAM, disco, procesos)
4. GET /health/safety/check?q=... -> evalúa si consulta es segura
5. Advanced Mode:
   - GET /advanced/profiles -> perfiles de sistema
   - GET /advanced/benchmarks -> resultados de benchmarks
   - GET /advanced/presets -> plantillas de prompt
   - GET /advanced/hardware -> info de hardware detectado
   - GET /advanced/history -> historial de inicios
   - GET /advanced/health -> monitoreo en tiempo real

## Flujo: Dev Tools

1. GET /dev/log?lines=300 -> tail de log del backend
2. GET /dev/log/stream -> SSE stream de log en tiempo real
3. GET /dev/traces?limit=30 -> lista de run traces
4. GET /dev/traces/{run_id} -> trace completo de una corrida
5. DELETE /dev/traces -> limpia traces
6. Cada trace incluye: plan versions, tool calls, outputs, veredicto

## Flujo: Configuración

1. GET /settings -> lee todas las vars de .env como flat map
2. POST /settings -> escribe keys SCREAMING_SNAKE_CASE en .env
3. Al guardar: reloaded config de config.py
4. Desktop SettingsView muestra todos los campos editables
5. Tauri helpers también pueden leer/escribir .env directamente sin backend

## Flujo: MCP Server

1. mcp_server.py inicia en puerto 8000
2. Expone herramientas via MCP protocol:
   - system_stats: uso de CPU, RAM, disco
   - check_query_safety: evalúa seguridad de consulta
   - rag_search: busca en vector store
   - folder_search: busca en filesystem
   - web_search: búsqueda web integrada
3. Se conecta al mismo LLM que el backend principal
4. Herramientas disponibles para agentes externos via MCP
ENDOFFILE
