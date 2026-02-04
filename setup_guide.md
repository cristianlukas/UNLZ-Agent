# Setup Guide: UNLZ Agent Integration

This guide explains how to connect your **UNLZ AI Studio**, **n8n**, and **Supabase** using this MCP server.

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

You can run the server directly to test it:

```powershell
python mcp_server.py
```

_Note: This server is designed to be used by an MCP Client (like Claude Desktop or n8n's MCP integration)._

## 3. Connecting to n8n (The "Agent")

Since n8n is running locally (or via Docker), you have two options to connect this Python script:

### Option A: Standard Output (stdio) - **Recommended for local n8n**

If you are running n8n locally via `npm` or desktop app:

1.  In n8n, look for "MCP" or "Model Context Protocol" execution nodes (if available in your version).
2.  Command: `python`
3.  Args: `C:\Users\Cristian\Documents\GitHub\UNLZ-Agent\mcp_server.py`

### Option B: SSE (Server Sent Events) - **For Docker/Remote n8n**

(Optional) If you need to expose this as a web server, modify `mcp_server.py` to use `mcp.run_sse()` instead of `mcp.run()`.

## 4. Connecting UNLZ AI Studio to the Internet (Web Bridge)

To let your n8n agent control the LLMs, you need to expose the UNLZ AI Studio API.

1.  Start UNLZ AI Studio: `python system/web_bridge.py` (Port 5000)
2.  Use **Cloudflare Tunnel** (Free) to expose it:
    ```powershell
    cloudflared tunnel --url http://localhost:5000
    ```
3.  Copy the `https://....trycloudflare.com` URL.
4.  In n8n, use this URL for your HTTP Request nodes to `/v1/chat/completions`.

## 5. RAG with Supabase

1.  Create a Supabase project (Free Tier).
2.  Enable the `pgvector` extension in SQL Editor: `create extension vector;`
3.  In n8n, use the **Supabase Vector Store** node to insert and retrieve documents.

## Diagram

refer to `README.md` for the architecture overview.
