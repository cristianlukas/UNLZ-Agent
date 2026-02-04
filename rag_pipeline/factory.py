from config import Config
from langchain_ollama import OllamaEmbeddings
from langchain_community.embeddings import OpenAIEmbeddings

# Factory for Embeddings
def get_embeddings():
    if Config.LLM_PROVIDER == "openai":
        return OpenAIEmbeddings(api_key=Config.OPENAI_API_KEY)
    else:
        # Default to Ollama
        return OllamaEmbeddings(model="qwen2.5-coder:14b", base_url=Config.OLLAMA_BASE_URL)

# Factory for Vector Store
def get_vector_store():
    embeddings = get_embeddings()

    if Config.VECTOR_DB_PROVIDER == "supabase":
        from langchain_community.vectorstores import SupabaseVectorStore
        from supabase import create_client
        
        supabase = create_client(Config.SUPABASE_URL, Config.SUPABASE_KEY)
        return SupabaseVectorStore(
            client=supabase,
            embedding=embeddings,
            table_name="documents",
            query_name="match_documents",
        )
    
    else:
        # Default to ChromaDB (Local)
        from langchain_chroma import Chroma
        
        return Chroma(
            collection_name="unlz_agent_docs",
            embedding_function=embeddings,
            persist_directory=Config.CHROMA_PERSIST_DIRECTORY,
        )
