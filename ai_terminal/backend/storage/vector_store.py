"""ChromaDB vector store for semantic command history search."""
from __future__ import annotations

import hashlib
from typing import Any, Dict, List, Optional

from backend.config import settings

# Lazy globals — heavy imports deferred to first use
_client = None
_collection = None
_embedder = None


def _get_client():
    global _client
    if _client is None:
        import chromadb
        _client = chromadb.PersistentClient(path=str(settings.CHROMA_PATH))
    return _client


def _get_collection():
    global _collection
    if _collection is None:
        _collection = _get_client().get_or_create_collection(
            name="commands",
            metadata={"hnsw:space": "cosine"},
        )
    return _collection


def _embed(texts: List[str]) -> List[List[float]]:
    global _embedder
    if _embedder is None:
        from sentence_transformers import SentenceTransformer
        print("[vector_store] Loading embedding model (first run may take a moment)…")
        _embedder = SentenceTransformer("all-MiniLM-L6-v2")
    return _embedder.encode(texts, show_progress_bar=False).tolist()


def add(text: str, metadata: Dict[str, Any]) -> None:
    """Embed and store a command entry."""
    if not settings.USE_VECTOR_STORE:
        return
    try:
        doc_id = hashlib.sha256(
            f"{text}{metadata.get('session_id', '')}{metadata.get('timestamp', '')}".encode()
        ).hexdigest()[:16]
        _get_collection().upsert(
            ids=[doc_id],
            embeddings=_embed([text]),
            documents=[text],
            metadatas=[{k: str(v) for k, v in metadata.items()}],
        )
    except Exception as e:
        print(f"[vector_store] add failed: {e}")


def search(query: str, n: int = 5, session_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """Semantic nearest-neighbour search over stored commands."""
    if not settings.USE_VECTOR_STORE:
        return []
    try:
        col = _get_collection()
        count = col.count()
        if count == 0:
            return []
        where = {"session_id": session_id} if session_id else None
        results = col.query(
            query_embeddings=_embed([query]),
            n_results=min(n, count),
            where=where,
            include=["documents", "metadatas", "distances"],
        )
        return [
            {"text": doc, "metadata": meta, "score": round(1 - dist, 4)}
            for doc, meta, dist in zip(
                results["documents"][0],
                results["metadatas"][0],
                results["distances"][0],
            )
        ]
    except Exception as e:
        print(f"[vector_store] search failed: {e}")
        return []
