from rag_pipeline.factory import get_vector_store
from config import Config

def search_documents(query: str, k: int = 4):
    """
    Search for relevant documents in the configured Vector DB.
    """
    try:
        Config.validate()
        vector_store = get_vector_store()
        
        # Perform similarity search
        results = vector_store.similarity_search(query, k=k)
        
        # Format results
        return [
            {
                "content": doc.page_content,
                "source": doc.metadata.get("source", "Unknown"),
                "page": doc.metadata.get("page", 0)
            }
            for doc in results
        ]
    except Exception as e:
        return [{"error": str(e)}]

if __name__ == "__main__":
    # Test
    print(search_documents("test query"))
