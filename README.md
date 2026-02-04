# UNLZ Agent: Autonomous Multi-Modal Assistant

[🇬🇧 English](README.md) | [🇪🇸 Español](README_ES.md)

This project is a **Multi-Modal Autonomous Agent** designed for flexible research and assistance. It orchestrates a local agentic workflow using **n8n**, integrating **Model Context Protocol (MCP)** for resource access and a flexible **RAG** pipeline for knowledge retrieval.

## Architecture

```mermaid
graph TD
    A[Local Knowledge Base<br/>/data folder] -->|MCP Protocol| B(MCP Server<br/>Python Script)
    B -->|Exposes Tools| C[n8n Workflow<br/>Local Agent Orchestrator]
    C -->|Stores/Retrieves| D[Supabase<br/>Vector DB & Memory]
    C -->|Search| E[Web Search Tool]
    C -->|LLM Inference| F[Ollama<br/>Localhost:11434]
    G[Web GUI<br/>Next.js] -->|Chat/Webhook| C
```

## System Capabilities

This application is engineered ensuring modularity, security, and scalability:

- **Hybrid RAG Architecture**: A flexible pipeline (`rag_pipeline/`) that supports both local persistence (ChromaDB) and cloud-based vector storage (Supabase), configurable via environment variables.
- **Security Guardrails**: Integrated input/output validation layer (`guardrails/`) to sanitise queries and prevent prompt injection attacks.
- **Extensible Tooling (MCP)**: Custom Model Context Protocol server exposing Python-based utilities to the agentic workflow.
- **Centralized Configuration**: Unified settings management (`config.py`) implementing the Factory pattern to switch between Local (Ollama) and Cloud (OpenAI) inference providers dynamically.
- **Modern Frontend**: A responsive Next.js web interface for agent interaction and system monitoring.

## Setup

### 1. Prerequisites

- Node.js 18+ (for Web GUI)
- Python 3.10+
- n8n (Self-hosted or Cloud)
- **LLM**: Ollama (Local) OR OpenAI (Cloud)
- **Vector DB**: ChromaDB (Local default) OR Supabase (Cloud)

### 2. Installation

1.  **Clone the repository**:

    ```bash
    git clone https://github.com/tu-usuario/UNLZ-Agent.git
    cd UNLZ-Agent
    ```

2.  **Set up Python Environment**:

    ```bash
    # Create virtual environment
    python -m venv venv

    # Activate virtual environment
    # Windows:
    .\venv\Scripts\activate
    # Mac/Linux:
    source venv/bin/activate

    # Install dependencies
    pip install -r requirements.txt
    ```

3.  **Set up Frontend**:

    ```bash
    cd frontend
    npm install
    # or
    yarn install
    ```

4.  **Configure Environment**:
    Create a `.env` file in the root directory (use established example if available):
    ```env
    # Example .env content
    VECTOR_DB_PROVIDER=chroma
    LLM_PROVIDER=ollama
    OLLAMA_BASE_URL=http://localhost:11434
    MCP_PORT=8000
    ```

### 3. Running the Application

This is a full-stack application. You only need to run the frontend, and it will automatically manage the backend (MCP Server) for you.

```bash
cd frontend
npm run dev
```

Open [http://localhost:3000](http://localhost:3000) in your browser. The "UNLZ Agent" backend will start automatically.
