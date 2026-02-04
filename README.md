# Autonomous University Researcher Agent

## Overview

This project transforms the **UNLZ AI Studio** into an autonomous research agent. It uses the **Model Context Protocol (MCP)** to expose local university resources (files, hardware stats) to an agentic workflow orchestrated by **n8n** and powered by **Supabase** for memory and RAG.

## Architecture

```mermaid
graph TD
    A[UNLZ AI Studio\nLocal PC] -->|MCP Protocol| B(MCP Server\nPython Script)
    B -->|Exposes Tools| C[n8n Workflow\nAgent Orchestrator]
    C -->|Stores/Retrieves| D[Supabase\nVector DB & Memory]
    C -->|Search| E[Web Search Tool]
    C -->|LLM Inference| F[Qwen 2.5\nvia Cloudflare/Ngrok]
```

## Setup

### 1. Prerequisites

- Python 3.10+
- n8n (Self-hosted)
- Supabase Account (Free Tier)
- UNLZ AI Studio installed

### 2. Installation

```bash
pip install -r requirements.txt
```

### 3. Running the MCP Server

```bash
python mcp_server.py
```
