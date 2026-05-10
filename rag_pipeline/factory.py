from config import Config


def get_embeddings():
    """Create the embeddings client configured for the active LLM provider.

    Purpose:
        Returns a provider-specific embeddings implementation compatible with
        the current runtime configuration.

    Parameters:
        None.

    Returns:
        Any: Embeddings client instance (`OpenAIEmbeddings` or
        `OllamaEmbeddings`).

    Raises:
        ImportError: If provider-specific dependencies are not installed.
        Exception: Any provider client initialization error is propagated.
    """
    if Config.LLM_PROVIDER == "openai":
        from langchain_openai import OpenAIEmbeddings
        return OpenAIEmbeddings(api_key=Config.OPENAI_API_KEY)

    elif Config.LLM_PROVIDER == "llamacpp":
        from langchain_openai import OpenAIEmbeddings
        llamacpp_base = f"http://{Config.LLAMACPP_HOST}:{Config.LLAMACPP_PORT}/v1"
        return OpenAIEmbeddings(
            api_key="not-needed",
            base_url=llamacpp_base,
            model=Config.LLAMACPP_MODEL_ALIAS,
        )

    else:
        from langchain_ollama import OllamaEmbeddings
        return OllamaEmbeddings(
            model=Config.OLLAMA_MODEL,
            base_url=Config.OLLAMA_BASE_URL,
        )


def get_vector_store():
    """Create the vector store backend configured for the project.

    Purpose:
        Builds either Supabase or Chroma vector store using the embeddings
        client returned by `get_embeddings()`.

    Parameters:
        None.

    Returns:
        Any: Configured vector store instance.

    Raises:
        ImportError: If required vector store dependencies are missing.
        Exception: Backend client initialization failures are propagated.
    """
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
        from langchain_chroma import Chroma

        return Chroma(
            collection_name="unlz_agent_docs",
            embedding_function=embeddings,
            persist_directory=Config.CHROMA_PERSIST_DIRECTORY,
        )
