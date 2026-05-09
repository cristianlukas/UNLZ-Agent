import os
from langchain_community.document_loaders import PyPDFLoader, DirectoryLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from config import Config
from rag_pipeline.factory import get_vector_store

def ingest_documents():
    print(f"Starting Ingestion via Provider: {Config.VECTOR_DB_PROVIDER.upper()}")
    print(f"Checking for documents in: {Config.DATA_DIR}")
    
    if not os.path.exists(Config.DATA_DIR):
        print(f"Data directory not found: {Config.DATA_DIR}")
        return

    # Validate Config
    try:
        Config.validate()
    except ValueError as e:
        print(f"Configuration Error: {e}")
        return

    # 1. Load PDFs
    loader = DirectoryLoader(Config.DATA_DIR, glob="**/*.pdf", loader_cls=PyPDFLoader)
    docs = loader.load()
    print(f"Loaded {len(docs)} documents.")

    if not docs:
        print("No PDFs found to ingest.")
        return

    # 2. Split Text
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000,
        chunk_overlap=200,
        add_start_index=True,
    )
    splits = text_splitter.split_documents(docs)
    print(f"Created {len(splits)} chunks.")

    # 3. Upsert to Vector Store
    print(f"Generating embeddings ({Config.LLM_PROVIDER}) and uploading to {Config.VECTOR_DB_PROVIDER}...")
    
    vector_store = get_vector_store()
    vector_store.add_documents(documents=splits)
    
    print("Ingestion complete!")

if __name__ == "__main__":
    ingest_documents()
