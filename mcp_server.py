import asyncio
import os
import psutil
from mcp.server.fastmcp import FastMCP
from guardrails.validator import validate_input

# Initialize the MCP server
mcp = FastMCP("UNLZ-Agent-Server")

# Configuration: Path to UNLZ AI Studio data
# Assuming UNLZ-Agent and UNLZ-AI-STUDIO are in the same parent directory (GitHub folder)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STUDIO_DATA_PATH = os.path.join(BASE_DIR, "..", "UNLZ-AI-STUDIO", "system", "data")

@mcp.tool()
def get_system_stats() -> dict:
    """
    Get current system hardware statistics (CPU, RAM, simulated GPU).
    Useful for the agent to decide which model limit to use.
    """
    cpu_percent = psutil.cpu_percent(interval=0.1)
    memory = psutil.virtual_memory()
    
    # Simulating GPU stats since we might not have nvidia-smi in this dev environment
    # In a real deployment, use pynvml or subprocess to call nvidia-smi
    gpu_stats = {
        "name": "NVIDIA GeForce RTX 3060 (Simulated)",
        "memory_total": 12288, # MB
        "memory_used": 4096,   # MB
        "utilization": 35      # Percent
    }

    return {
        "cpu_usage_percent": cpu_percent,
        "ram_total_gb": round(memory.total / (1024**3), 2),
        "ram_available_gb": round(memory.available / (1024**3), 2),
        "ram_percent": memory.percent,
        "gpu_stats": gpu_stats
    }

@mcp.tool()
def check_query_safety(query: str) -> dict:
    """
    Validate if a user query is safe to process (Guardrails).
    Returns {"valid": true/false, "error": "..."}
    """
    return validate_input(query)

from rag_pipeline.ingest import ingest_documents
from rag_pipeline.retriever import search_documents

@mcp.tool()
def trigger_rag_ingestion() -> str:
    """
    Trigger the RAG ingestion process.
    Reads PDFs from system/data, chunks them, and uploads to Vectors configuration (Local/Cloud).
    Returns a status message.
    """
    try:
        ingest_documents()
        return "RAG Ingestion completed successfully."
    except Exception as e:
        return f"Error during RAG ingestion: {str(e)}"

@mcp.tool()
def search_local_knowledge(query: str) -> list[dict]:
    """
    Search the local knowledge base (RAG) for relevant information.
    Use this for questions about university regulations, documents, or internal data.
    Returns a list of matching document chunks.
    """
    return search_documents(query)

from duckduckgo_search import DDGS
from datetime import datetime

@mcp.tool()
def web_search(query: str, max_results: int = 3) -> list[dict]:
    """
    Search the internet for current events, news, or general information.
    Use this for questions about 'current prices', 'latest news', or topics not in local docs.
    """
    try:
        results = DDGS().text(query, max_results=max_results)
        return results if results else [{"error": "No results found."}]
    except Exception as e:
        return [{"error": f"Search failed: {str(e)}"}]

@mcp.tool()
def get_current_time() -> str:
    """
    Get the current local date and time.
    """
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

@mcp.tool()
def list_knowledge_base_files() -> list[str]:
    """
    List files available in the UNLZ AI Studio system/data directory.
    These files might contain user configurations, logs, or knowledge base items.
    """
    if not os.path.exists(STUDIO_DATA_PATH):
        return [f"Error: Directory not found at {STUDIO_DATA_PATH}"]
    
    try:
        files = []
        for filename in os.listdir(STUDIO_DATA_PATH):
            full_path = os.path.join(STUDIO_DATA_PATH, filename)
            if os.path.isfile(full_path):
                files.append(filename)
        return files
    except Exception as e:
        return [f"Error listing files: {str(e)}"]

@mcp.tool()
def read_studio_file(filename: str) -> str:
    """
    Read the content of a specific file from the UNLZ AI Studio data directory.
    Args:
        filename: The name of the file to read (must be in system/data).
    """
    safe_filename = os.path.basename(filename)
    file_path = os.path.join(STUDIO_DATA_PATH, safe_filename)
    
    if not os.path.exists(file_path):
        return f"Error: File '{safe_filename}' not found."
    
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        return f"Error reading file: {str(e)}"

if __name__ == "__main__":
    print(f"Starting UNLZ Agent MCP Server...")
    print(f"Monitoring Data Path: {STUDIO_DATA_PATH}")
    # Run with SSE transport on port 8000 for local connectivity (n8n/Next.js)
    try:
        mcp.run(transport="sse", port=8000)
    except Exception as e:
        print(f"Server Error: {e}")
