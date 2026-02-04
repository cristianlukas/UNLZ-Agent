import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

class Config:
    # Provider Settings
    VECTOR_DB_PROVIDER = os.getenv("VECTOR_DB_PROVIDER", "chroma").lower() # chroma | supabase
    LLM_PROVIDER = os.getenv("LLM_PROVIDER", "ollama").lower() # ollama | openai
    
    # Paths
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    RAG_STORAGE_PATH = os.path.join(BASE_DIR, "rag_storage")
    DATA_DIR = os.path.join(BASE_DIR, "..", "UNLZ-AI-STUDIO", "system", "data")

    # Supabase (Optional)
    SUPABASE_URL = os.getenv("SUPABASE_URL", "")
    SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")

    # ChromaDB (Optional)
    CHROMA_PERSIST_DIRECTORY = RAG_STORAGE_PATH

    # LLM Settings
    OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

    @staticmethod
    def validate():
        if Config.VECTOR_DB_PROVIDER == "supabase":
            if not Config.SUPABASE_URL or not Config.SUPABASE_KEY:
                raise ValueError("Supabase provider requires SUPABASE_URL and SUPABASE_KEY")
        
        if Config.LLM_PROVIDER == "openai":
            if not Config.OPENAI_API_KEY:
                raise ValueError("OpenAI provider requires OPENAI_API_KEY")

# Ensure storage directory exists for Chroma
if not os.path.exists(Config.RAG_STORAGE_PATH):
    os.makedirs(Config.RAG_STORAGE_PATH)
