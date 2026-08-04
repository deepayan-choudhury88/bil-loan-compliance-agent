from __future__ import annotations
import os
from pathlib import Path

# Workaround for macOS OpenMP runtime duplication issues when loading FAISS.
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

from langchain_community.document_loaders import PyPDFLoader
from langchain_community.vectorstores import FAISS
from langchain_text_splitters import RecursiveCharacterTextSplitter
from dotenv import load_dotenv

from retrieval.provider import create_embeddings, validate_provider_environment

load_dotenv(override=True)

"""Build and persist a FAISS vector store from company-reference.pdf.
"""

DEFAULT_PDF_PATH = Path("data/company-reference.pdf")
DEFAULT_INDEX_DIR = Path("retrieval/vector_store/company_reference_faiss")
DEFAULT_EMBEDDING_MODEL = "text-embedding-3-small"
DEFAULT_CHUNK_SIZE = 1000
DEFAULT_CHUNK_OVERLAP = 150


def build_vector_store(
    pdf_path: Path = DEFAULT_PDF_PATH,
    index_dir: Path = DEFAULT_INDEX_DIR,
    embedding_model: str = DEFAULT_EMBEDDING_MODEL,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> Path:
    """Load PDF, split it, embed chunks, and persist FAISS index locally."""
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF file not found: {pdf_path}")

    loader = PyPDFLoader(str(pdf_path))
    documents = loader.load()

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=["\n\n", "\n", " ", ""],
    )
    chunks = splitter.split_documents(documents)

    embeddings = create_embeddings(default_model=embedding_model)
    vector_store = FAISS.from_documents(chunks, embeddings)

    index_dir.mkdir(parents=True, exist_ok=True)
    vector_store.save_local(str(index_dir))
    return index_dir


def main() -> None:
    """Entrypoint for one-time ingestion."""
    validate_provider_environment()

    pdf_path = Path(os.getenv("RAG_PDF_PATH", str(DEFAULT_PDF_PATH)))
    index_dir = Path(os.getenv("RAG_INDEX_DIR", str(DEFAULT_INDEX_DIR)))
    embedding_model = os.getenv("RAG_EMBEDDING_MODEL", DEFAULT_EMBEDDING_MODEL)

    saved_path = build_vector_store(
        pdf_path=pdf_path,
        index_dir=index_dir,
        embedding_model=embedding_model,
    )
    print(f"FAISS index saved at: {saved_path}")


if __name__ == "__main__":
    main()
