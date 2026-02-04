# Guía de Configuración: Integración del Agente UNLZ

[🇬🇧 English](setup_guide.md) | [🇪🇸 Español](setup_guide_ES.md)

Esta guía explica cómo conectar **Ollama**, **n8n Local** y **Supabase** utilizando este servidor MCP.

## 1. Configuración del Entorno

### Instalar Dependencias

Abre una terminal en esta carpeta y ejecuta:

```powershell
pip install -r requirements.txt
```

### Verificar la Ruta de UNLZ AI Studio

Asegúrate de que la estructura de carpetas se vea así:

```
Documents/GitHub/
├── UNLZ-AI-STUDIO/
│   └── system/
│       └── data/  <-- El servidor MCP busca aquí
└── UNLZ-Agent/    <-- Este repositorio
    └── mcp_server.py
```

## 2. Ejecutar el Servidor MCP

Ejecuta el servidor para exponer las herramientas locales:

```powershell
python mcp_server.py
```

### Configuración RAG (Variables de Entorno)

Para habilitar el pipeline RAG, debes configurar estas variables antes de correr el servidor:

```powershell
$env:SUPABASE_URL="tu-url-del-proyecto"
$env:SUPABASE_KEY="tu-clave-anonima"
python mcp_server.py
```

## 3. Ejecutar Ollama (LLM Sin Autenticación)

1.  Descarga e instala [Ollama](https://ollama.com/).
2.  Descarga un modelo (ej. Qwen 2.5 Coder, excelente para esta tarea):
    ```powershell
    ollama pull qwen2.5-coder:14b
    ```
3.  Verifica que esté corriendo en `http://localhost:11434`.

## 4. Configurar n8n Local

### Ejecutando n8n

Si estás ejecutando n8n vía Docker, necesitas asegurarte de que pueda alcanzar el Ollama y el servidor MCP de tu máquina anfitriona.

- Accede a los servicios del host usando `http://host.docker.internal:11434` (Ollama) y `http://host.docker.internal:8000` (MCP).

### Configuración del Flujo de Trabajo

1.  Importa `n8n_workflow.json`.
2.  **Nodo Ollama**: Asegúrate de que la URL Base esté configurada en `http://host.docker.internal:11434` (si usas Docker) o `http://localhost:11434` (si es nativo).
3.  **Supabase**: Conecta tus credenciales del plan gratuito para el Vector Store.

## 5. RAG con Supabase

1.  Crea un proyecto en Supabase (Plan Gratuito).
2.  Habilita la extensión `pgvector` en el Editor SQL: `create extension vector;`
3.  En n8n, usa el nodo **Supabase Vector Store** para insertar y recuperar documentos.

## Diagrama

referirse a `README_ES.md` para la descripción general de la arquitectura.
