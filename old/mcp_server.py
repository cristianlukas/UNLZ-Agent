import asyncio
import os
import subprocess
import psutil
from mcp.server.fastmcp import FastMCP
from guardrails.validator import validate_input
from config import Config

mcp = FastMCP("UNLZ-Agent-Server")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STUDIO_DATA_PATH = os.path.join(BASE_DIR, "..", "UNLZ-AI-STUDIO", "system", "data")

# Holds the llama.cpp subprocess when managed by this server
_llamacpp_proc: subprocess.Popen | None = None


@mcp.tool()
def get_system_stats() -> dict:
    """Get current system hardware statistics (CPU, RAM, simulated GPU)."""
    cpu_percent = psutil.cpu_percent(interval=0.1)
    memory = psutil.virtual_memory()

    gpu_stats = {
        "name": "NVIDIA GeForce RTX 3060 (Simulated)",
        "memory_total": 12288,
        "memory_used": 4096,
        "utilization": 35,
    }

    return {
        "cpu_usage_percent": cpu_percent,
        "ram_total_gb": round(memory.total / (1024**3), 2),
        "ram_available_gb": round(memory.available / (1024**3), 2),
        "ram_percent": memory.percent,
        "gpu_stats": gpu_stats,
    }


@mcp.tool()
def check_query_safety(query: str) -> dict:
    """Validate if a user query is safe to process (Guardrails)."""
    return validate_input(query)


from rag_pipeline.ingest import ingest_documents
from rag_pipeline.retriever import search_documents


@mcp.tool()
def trigger_rag_ingestion() -> str:
    """Trigger RAG ingestion: reads PDFs from data/, chunks them, stores in vector DB."""
    try:
        ingest_documents()
        return "RAG Ingestion completed successfully."
    except Exception as e:
        return f"Error during RAG ingestion: {str(e)}"


@mcp.tool()
def search_local_knowledge(query: str) -> list[dict]:
    """Search the local knowledge base (RAG) for relevant document chunks."""
    return search_documents(query)


from duckduckgo_search import DDGS
from datetime import datetime


@mcp.tool()
def web_search(query: str, max_results: int = 3) -> list[dict]:
    """Search the internet via DuckDuckGo for current information."""
    try:
        results = DDGS().text(query, max_results=max_results)
        return results if results else [{"error": "No results found."}]
    except Exception as e:
        return [{"error": f"Search failed: {str(e)}"}]


@mcp.tool()
def get_current_time() -> str:
    """Get the current local date and time."""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


@mcp.tool()
def list_knowledge_base_files() -> list[str]:
    """List files in the UNLZ AI Studio data directory."""
    if not os.path.exists(STUDIO_DATA_PATH):
        return [f"Error: Directory not found at {STUDIO_DATA_PATH}"]
    try:
        return [f for f in os.listdir(STUDIO_DATA_PATH)
                if os.path.isfile(os.path.join(STUDIO_DATA_PATH, f))]
    except Exception as e:
        return [f"Error listing files: {str(e)}"]


@mcp.tool()
def read_studio_file(filename: str) -> str:
    """Read a file from the UNLZ AI Studio data directory."""
    safe_filename = os.path.basename(filename)
    file_path = os.path.join(STUDIO_DATA_PATH, safe_filename)
    if not os.path.exists(file_path):
        return f"Error: File '{safe_filename}' not found."
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        return f"Error reading file: {str(e)}"


# ─── llama.cpp process management ───────────────────────────────────────────

def _build_llamacpp_args() -> list[str]:
    """Build the argument list for llama-server from Config."""
    args = [
        Config.LLAMACPP_EXECUTABLE,
        "-m", Config.LLAMACPP_MODEL_PATH,
        "--alias", Config.LLAMACPP_MODEL_ALIAS,
        "--host", Config.LLAMACPP_HOST,
        "--port", str(Config.LLAMACPP_PORT),
        "-c", str(Config.LLAMACPP_CONTEXT_SIZE),
        "-ngl", str(Config.LLAMACPP_N_GPU_LAYERS),
    ]
    if Config.LLAMACPP_FLASH_ATTN:
        args.append("--flash-attn")
    if Config.LLAMACPP_CACHE_TYPE_K:
        args += ["--cache-type-k", Config.LLAMACPP_CACHE_TYPE_K]
    if Config.LLAMACPP_CACHE_TYPE_V:
        args += ["--cache-type-v", Config.LLAMACPP_CACHE_TYPE_V]
    if Config.LLAMACPP_EXTRA_ARGS:
        args += Config.LLAMACPP_EXTRA_ARGS.split()
    return args


@mcp.tool()
def start_llamacpp_server() -> dict:
    """Start the llama.cpp server using settings from config. Returns status and pid."""
    global _llamacpp_proc

    if not Config.LLAMACPP_EXECUTABLE:
        return {"success": False, "error": "LLAMACPP_EXECUTABLE not configured"}
    if not Config.LLAMACPP_MODEL_PATH:
        return {"success": False, "error": "LLAMACPP_MODEL_PATH not configured"}
    if not os.path.isfile(Config.LLAMACPP_EXECUTABLE):
        return {"success": False, "error": f"Executable not found: {Config.LLAMACPP_EXECUTABLE}"}
    if not os.path.isfile(Config.LLAMACPP_MODEL_PATH):
        return {"success": False, "error": f"Model not found: {Config.LLAMACPP_MODEL_PATH}"}

    if _llamacpp_proc and _llamacpp_proc.poll() is None:
        return {"success": True, "status": "already_running", "pid": _llamacpp_proc.pid}

    try:
        args = _build_llamacpp_args()
        _llamacpp_proc = subprocess.Popen(
            args,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        return {
            "success": True,
            "status": "started",
            "pid": _llamacpp_proc.pid,
            "url": f"http://{Config.LLAMACPP_HOST}:{Config.LLAMACPP_PORT}/v1",
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool()
def stop_llamacpp_server() -> dict:
    """Stop the llama.cpp server if it was started by this MCP server."""
    global _llamacpp_proc

    if _llamacpp_proc is None:
        return {"success": True, "status": "not_running"}

    if _llamacpp_proc.poll() is not None:
        _llamacpp_proc = None
        return {"success": True, "status": "already_stopped"}

    _llamacpp_proc.terminate()
    try:
        _llamacpp_proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        _llamacpp_proc.kill()
    _llamacpp_proc = None
    return {"success": True, "status": "stopped"}


@mcp.tool()
def get_llamacpp_status() -> dict:
    """Check if the llama.cpp server is running and return its config."""
    import urllib.request

    base_url = f"http://{Config.LLAMACPP_HOST}:{Config.LLAMACPP_PORT}"
    running = False
    try:
        with urllib.request.urlopen(f"{base_url}/health", timeout=2) as r:
            running = r.status == 200
    except Exception:
        pass

    managed_pid = _llamacpp_proc.pid if (_llamacpp_proc and _llamacpp_proc.poll() is None) else None

    return {
        "running": running,
        "managed_pid": managed_pid,
        "base_url": base_url,
        "model_path": Config.LLAMACPP_MODEL_PATH,
        "model_alias": Config.LLAMACPP_MODEL_ALIAS,
        "context_size": Config.LLAMACPP_CONTEXT_SIZE,
    }


@mcp.tool()
def direct_chat(message: str, use_rag: bool = True, system_prompt: str = "") -> dict:
    """
    Chat directly with the configured LLM (llamacpp/ollama/openai) bypassing n8n.
    Optionally enriches the prompt with local RAG context.
    """
    import urllib.request
    import json

    # Build RAG context
    rag_context = ""
    if use_rag:
        try:
            docs = search_documents(message)
            if docs:
                rag_context = "\n\n".join(
                    d.get("page_content") or d.get("content") or json.dumps(d)
                    for d in docs
                )
        except Exception:
            pass

    default_prompts = {
        "en": "You are a helpful assistant for Universidad Nacional de Lomas de Zamora.",
        "es": "Eres un asistente útil de la Universidad Nacional de Lomas de Zamora.",
        "zh": "您是洛马斯·德萨莫拉国立大学的助理。",
    }
    sys_prompt = system_prompt or default_prompts.get(Config.AGENT_LANGUAGE, default_prompts["en"])
    if rag_context:
        sys_prompt += f"\n\nRelevant context:\n{rag_context}"

    messages = [
        {"role": "system", "content": sys_prompt},
        {"role": "user", "content": message},
    ]

    # Determine endpoint + model
    provider = Config.LLM_PROVIDER
    if provider == "llamacpp":
        base_url = f"http://{Config.LLAMACPP_HOST}:{Config.LLAMACPP_PORT}/v1"
        model = Config.LLAMACPP_MODEL_ALIAS
        api_key = "not-needed"
    elif provider == "openai":
        base_url = "https://api.openai.com/v1"
        model = Config.OPENAI_MODEL
        api_key = Config.OPENAI_API_KEY
    else:
        ollama_base = Config.OLLAMA_BASE_URL.rstrip("/")
        base_url = f"{ollama_base}/v1"
        model = Config.OLLAMA_MODEL
        api_key = "not-needed"

    payload = json.dumps({"model": model, "messages": messages, "stream": False}).encode()
    req = urllib.request.Request(
        f"{base_url}/chat/completions",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            data = json.loads(r.read())
        response_text = data["choices"][0]["message"]["content"]
        return {"success": True, "response": response_text, "provider": provider}
    except Exception as e:
        return {"success": False, "error": str(e), "provider": provider}


if __name__ == "__main__":
    from dotenv import load_dotenv
    import uvicorn

    load_dotenv()

    port = Config.MCP_PORT
    print(f"Starting UNLZ Agent MCP Server on port {port}")
    print(f"LLM Provider: {Config.LLM_PROVIDER}")
    print(f"n8n enabled: {Config.N8N_ENABLED}")
    if Config.LLM_PROVIDER == "llamacpp":
        print(f"llama.cpp model: {Config.LLAMACPP_MODEL_PATH}")
        print(f"llama.cpp server: http://{Config.LLAMACPP_HOST}:{Config.LLAMACPP_PORT}")

    try:
        uvicorn.run(mcp.sse_app, host="0.0.0.0", port=port)
    except Exception as e:
        print(f"Server Error: {e}")
