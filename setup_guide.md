# Setup Guide: UNLZ Agent Integration

[🇬🇧 English](setup_guide.md) | [🇪🇸 Español](setup_guide_ES.md)

This guide explains how to connect your **Ollama**, **Local n8n**, and **Supabase** using this MCP server.

## 1. Environment Setup

### Install Dependencies

Open a terminal in this folder and run:

```powershell
pip install -r requirements.txt
```

### Verify UNLZ AI Studio Path

Ensure your folder structure looks like this:

```
Documents/GitHub/
├── UNLZ-AI-STUDIO/
│   └── system/
│       └── data/  <-- The MCP server looks here
└── UNLZ-Agent/    <-- This repository
    └── mcp_server.py
```

## 2. Running the MCP Server

Run the server to expose local tools:

```powershell
python mcp_server.py
```

## 3. Running Ollama (Authentication-Free LLM)

1.  Download and install [Ollama](https://ollama.com/).
2.  Pull a model (e.g., Qwen 2.5 Coder, excellent for this task):
    ```powershell
    ollama pull qwen2.5-coder:14b
    ```
3.  Verify it's running at `http://localhost:11434`.

## 4. Configuring Local n8n

### Running n8n

If you are running n8n via Docker, you need to ensure it can reach your host machine's Ollama and MCP server.

- Access host services using `http://host.docker.internal:11434` (Ollama) and `http://host.docker.internal:8000` (MCP).

### Workflow Setup

1.  Import `n8n_workflow.json`.
2.  **Ollama Node**: Ensure the Base URL is set to `http://host.docker.internal:11434` (if in Docker) or `http://localhost:11434` (if native).
3.  **Supabase**: Connect your free tier credentials for the Vector Store.

## 5. RAG with Supabase

1.  Create a Supabase project (Free Tier).
2.  Enable the `pgvector` extension in SQL Editor: `create extension vector;`
3.  In n8n, use the **Supabase Vector Store** node to insert and retrieve documents.

## 6. Running the Web GUI (Frontend)

The project includes a modern Next.js interface.

1.  Open a new terminal.
2.  Navigate to the frontend folder:
    ```powershell
    cd frontend
    ```
3.  Start the development server:
    ```powershell
    npm run dev
    ```
4.  Open [http://localhost:3000](http://localhost:3000) in your browser.

## Diagram

refer to `README.md` for the architecture overview.
