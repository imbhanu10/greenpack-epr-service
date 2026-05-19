"""Lightweight RAG question-answering service."""

from pathlib import Path
from typing import Any
import warnings

import chromadb

with warnings.catch_warnings():
    warnings.simplefilter("ignore", FutureWarning)
    import google.generativeai as genai
from langchain_text_splitters import RecursiveCharacterTextSplitter
from sentence_transformers import SentenceTransformer

from app.core.config import settings


BASE_DIR = Path(__file__).resolve().parents[2]
DOCUMENTS_PATH = BASE_DIR / "data" / "documents"
UNKNOWN_ANSWER = "I do not know based on the provided documents"
RAG_UNAVAILABLE_ANSWER = "RAG answer generation is currently unavailable."

_embedding_model: SentenceTransformer | None = None
_gemini_model: Any | None = None
_chroma_client: Any | None = None
_collection: Any | None = None


def get_embedding_model() -> SentenceTransformer:
    """Return the lazily initialized sentence-transformers model."""
    global _embedding_model

    if _embedding_model is None:
        _embedding_model = SentenceTransformer("all-MiniLM-L6-v2")

    return _embedding_model


def get_gemini_model() -> Any:
    """Return the lazily initialized Gemini model."""
    global _gemini_model

    if _gemini_model is None:
        if not settings.GEMINI_API_KEY:
            raise RuntimeError("GEMINI_API_KEY is not configured.")

        genai.configure(api_key=settings.GEMINI_API_KEY)
        _gemini_model = genai.GenerativeModel(settings.GEMINI_MODEL)

    return _gemini_model


def get_collection() -> Any:
    """Return the lazily initialized ChromaDB collection."""
    global _chroma_client
    global _collection

    if _chroma_client is None:
        _chroma_client = chromadb.Client()

    if _collection is None:
        _collection = _chroma_client.get_or_create_collection(
            name="epr_documents",
        )

    return _collection


def load_documents() -> list[dict[str, str]]:
    """Load all text documents from the documents directory."""
    documents: list[dict[str, str]] = []

    for file_path in sorted(DOCUMENTS_PATH.glob("*.txt")):
        content = file_path.read_text(encoding="utf-8")

        documents.append(
            {
                "source": file_path.name,
                "content": content,
            }
        )

    return documents


def ingest_documents() -> None:
    """Chunk and store documents in ChromaDB."""
    collection = get_collection()
    existing = collection.count()

    # Prevent duplicate ingestion
    if existing > 0:
        return

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=500,
        chunk_overlap=50,
    )

    documents = load_documents()

    doc_id = 0
    embedding_model = get_embedding_model()

    for document in documents:
        chunks = splitter.split_text(document["content"])

        for chunk in chunks:
            embedding = embedding_model.encode(chunk).tolist()

            collection.add(
                ids=[str(doc_id)],
                documents=[chunk],
                embeddings=[embedding],
                metadatas=[
                    {
                        "source": document["source"]
                    }
                ],
            )

            doc_id += 1


def retrieve_context(question: str, top_k: int = 3) -> dict[str, list[str]]:
    """Retrieve relevant context from ChromaDB."""
    try:
        collection = get_collection()

        if collection.count() == 0:
            return {
                "documents": [],
                "sources": [],
            }

        query_embedding = get_embedding_model().encode(question).tolist()

        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
        )
    except Exception:
        return {
            "documents": [],
            "sources": [],
        }

    documents_nested = results.get("documents") or []
    metadatas_nested = results.get("metadatas") or []

    if not documents_nested or not documents_nested[0]:
        return {
            "documents": [],
            "sources": [],
        }

    documents = [
        document
        for document in documents_nested[0]
        if isinstance(document, str) and document.strip()
    ]
    metadatas = metadatas_nested[0] if metadatas_nested else []

    if not documents:
        return {
            "documents": [],
            "sources": [],
        }

    return {
        "documents": documents,
        "sources": sorted(
            {
                metadata.get("source")
                for metadata in metadatas
                if isinstance(metadata, dict)
                and isinstance(metadata.get("source"), str)
            }
        ),
    }


def answer_question(question: str) -> dict[str, list[str] | str]:
    """Answer questions using retrieved EPR compliance context."""
    try:
        ingest_documents()
    except Exception:
        return {
            "answer": UNKNOWN_ANSWER,
            "citations": [],
        }

    retrieved = retrieve_context(question)

    context = "\n\n".join(retrieved["documents"])

    if not context.strip():
        return {
            "answer": UNKNOWN_ANSWER,
            "citations": [],
        }

    prompt = f"""
You are an EPR compliance assistant.

Answer ONLY using the provided context.

If the answer is not contained in the context,
respond with:
"I do not know based on the provided documents"

Context:
{context}

Question:
{question}
"""

    try:
        response = get_gemini_model().generate_content(
            prompt,
            generation_config={
                "temperature": 0.2,
            },
        )
        answer = response.text.strip()
    except Exception:
        return {
            "answer": RAG_UNAVAILABLE_ANSWER,
            "citations": [],
        }

    # Anti-hallucination safeguard
    if (
        "do not know" in answer.lower()
        or len(answer) < 10
    ):
        return {
            "answer": UNKNOWN_ANSWER,
            "citations": [],
        }

    return {
        "answer": answer,
        "citations": retrieved["sources"],
    }
