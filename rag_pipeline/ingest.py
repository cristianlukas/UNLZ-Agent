import os
import sys
from supabase import create_client, Client
from langchain_community.document_loaders import PyPDFLoader, DirectoryLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_ollama import OllamaEmbeddings
from langchain_community.vectorstores import SupabaseVectorStore

# Configuration
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "UNLZ-AI-STUDIO", "system", "data")

def ingest_documents():
    print(f"Checking for documents in: {DATA_DIR}")
    if not os.path.exists(DATA_DIR):
        print("Data directory not found.")
        return

    if not SUPABASE_URL or not SUPABASE_KEY:
        print("Error: SUPABASE_URL and SUPABASE_KEY environment variables must be set.")
        return

    # 1. Load PDFs
    loader = DirectoryLoader(DATA_DIR, glob="**/*.pdf", loader_cls=PyPDFLoader)
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

    # 3. Create Embeddings & Upsert to Supabase
    print("Generating embeddings and uploading to Supabase...")
    embeddings = OllamaEmbeddings(model="qwen2.5-coder:14b", base_url="http://localhost:11434")
    
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
    
    vector_store = SupabaseVectorStore.from_documents(
        splits,
        embeddings,
        client=supabase,
        table_name="documents",
        query_name="match_documents",
    )
    print("Ingestion complete!")

if __name__ == "__main__":
    ingest_documents()
