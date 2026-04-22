import os
import sys
from pathlib import Path
from dotenv import load_dotenv

def _runtime_root_dir() -> Path:
    override = (os.getenv("UNLZ_PROJECT_ROOT") or "").strip()
    if override:
        return Path(override)
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
        if exe_dir.name.lower() == "binaries":
            return exe_dir.parent
        return exe_dir
    return Path(__file__).parent

load_dotenv(dotenv_path=_runtime_root_dir() / ".env")

class Config:
    # Provider Settings
    VECTOR_DB_PROVIDER = os.getenv("VECTOR_DB_PROVIDER", "chroma").lower()  # chroma | supabase
    LLM_PROVIDER = os.getenv("LLM_PROVIDER", "ollama").lower()              # ollama | openai | llamacpp
    AGENT_LANGUAGE = os.getenv("AGENT_LANGUAGE", "en").lower()              # en | es | zh
    MCP_PORT = int(os.getenv("MCP_PORT", "8000"))
    AGENT_EXECUTION_MODE = os.getenv("AGENT_EXECUTION_MODE", "confirm").lower()  # confirm | autonomous
    AGENT_COMMAND_TIMEOUT_SEC = int(os.getenv("AGENT_COMMAND_TIMEOUT_SEC", "60"))
    AGENT_COMMAND_MAX_OUTPUT = int(os.getenv("AGENT_COMMAND_MAX_OUTPUT", "4000"))
    WEB_SEARCH_ENGINE = os.getenv("WEB_SEARCH_ENGINE", "google").lower()    # google | duckduckgo | serpapi | bing | fusion | auto

    # Paths
    BASE_DIR = str(_runtime_root_dir())
    RAG_STORAGE_PATH = os.path.join(BASE_DIR, "rag_storage")
    DATA_DIR = os.path.join(BASE_DIR, "data")

    # Supabase (Optional)
    SUPABASE_URL = os.getenv("SUPABASE_URL", "")
    SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")

    # ChromaDB
    CHROMA_PERSIST_DIRECTORY = RAG_STORAGE_PATH

    # Ollama Settings
    OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5-coder:14b")

    # OpenAI Settings
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
    OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    # llama.cpp Settings
    LLAMACPP_EXECUTABLE = os.getenv("LLAMACPP_EXECUTABLE", "")
    LLAMACPP_MODEL_PATH = os.getenv("LLAMACPP_MODEL_PATH", "")
    LLAMACPP_HOST = os.getenv("LLAMACPP_HOST", "127.0.0.1")
    LLAMACPP_PORT = int(os.getenv("LLAMACPP_PORT", "8080"))
    LLAMACPP_CONTEXT_SIZE = int(os.getenv("LLAMACPP_CONTEXT_SIZE", "32768"))
    LLAMACPP_N_GPU_LAYERS = int(os.getenv("LLAMACPP_N_GPU_LAYERS", "999"))
    LLAMACPP_FLASH_ATTN = os.getenv("LLAMACPP_FLASH_ATTN", "true").lower() == "true"
    LLAMACPP_MODEL_ALIAS = os.getenv("LLAMACPP_MODEL_ALIAS", "local-model")
    LLAMACPP_CACHE_TYPE_K = os.getenv("LLAMACPP_CACHE_TYPE_K", "")
    LLAMACPP_CACHE_TYPE_V = os.getenv("LLAMACPP_CACHE_TYPE_V", "")
    LLAMACPP_EXTRA_ARGS = os.getenv("LLAMACPP_EXTRA_ARGS", "")
    LLAMACPP_MODELS_DIR = os.getenv("LLAMACPP_MODELS_DIR", "")

    # n8n Settings
    N8N_ENABLED = os.getenv("N8N_ENABLED", "true").lower() == "true"
    N8N_WEBHOOK_URL = os.getenv("N8N_WEBHOOK_URL", "http://127.0.0.1:5678/webhook/chat")

    @staticmethod
    def validate():
        if Config.AGENT_EXECUTION_MODE not in ("confirm", "autonomous"):
            raise ValueError("AGENT_EXECUTION_MODE must be 'confirm' or 'autonomous'")
        if Config.WEB_SEARCH_ENGINE not in ("google", "duckduckgo", "serpapi", "bing", "fusion", "auto"):
            raise ValueError("WEB_SEARCH_ENGINE must be one of: google, duckduckgo, serpapi, bing, fusion, auto")

        if Config.VECTOR_DB_PROVIDER == "supabase":
            if not Config.SUPABASE_URL or not Config.SUPABASE_KEY:
                raise ValueError("Supabase provider requires SUPABASE_URL and SUPABASE_KEY")

        if Config.LLM_PROVIDER == "openai":
            if not Config.OPENAI_API_KEY:
                raise ValueError("OpenAI provider requires OPENAI_API_KEY")

        if Config.LLM_PROVIDER == "llamacpp":
            if not Config.LLAMACPP_EXECUTABLE:
                raise ValueError("llama.cpp provider requires LLAMACPP_EXECUTABLE")
            if not Config.LLAMACPP_MODEL_PATH:
                raise ValueError("llama.cpp provider requires LLAMACPP_MODEL_PATH")

if not os.path.exists(Config.RAG_STORAGE_PATH):
    os.makedirs(Config.RAG_STORAGE_PATH)
