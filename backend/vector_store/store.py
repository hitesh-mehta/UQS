"""
Vector Store Abstraction — FAISS-based embedding storage and retrieval.
Supports: FAISS (local, hackathon-ready), Qdrant (production).

Each document chunk is stored with:
  - Embedding vector
  - Metadata (source file, page number, chunk index)
  - Raw text
"""
from __future__ import annotations

import json
import os
import pickle
from pathlib import Path
from typing import Optional

import numpy as np
from sentence_transformers import SentenceTransformer

from backend.config import settings


# ── Chunk Model ───────────────────────────────────────────────────────────────

class Chunk:
    def __init__(
        self,
        text: str,
        source: str,
        page: Optional[int] = None,
        chunk_index: int = 0,
        metadata: dict | None = None,
    ):
        self.text = text
        self.source = source
        self.page = page
        self.chunk_index = chunk_index
        self.metadata = metadata or {}

    def to_dict(self) -> dict:
        return {
            "text": self.text,
            "source": self.source,
            "page": self.page,
            "chunk_index": self.chunk_index,
            "metadata": self.metadata,
        }


# ── Embedder ──────────────────────────────────────────────────────────────────

class Embedder:
    """Wraps sentence-transformers for text embedding."""
    _model: SentenceTransformer | None = None

    @classmethod
    def get_model(cls) -> SentenceTransformer:
        if cls._model is None:
            cls._model = SentenceTransformer(settings.embedding_model)
        return cls._model

    @classmethod
    def embed(cls, texts: list[str]) -> np.ndarray:
        model = cls.get_model()
        return model.encode(texts, normalize_embeddings=True, show_progress_bar=False)

    @classmethod
    def embed_single(cls, text: str) -> np.ndarray:
        return cls.embed([text])[0]


# ── FAISS Store ───────────────────────────────────────────────────────────────

class FAISSVectorStore:
    """
    Local FAISS vector store. Persists index + metadata to disk.
    Thread-safe for single-process use (add locks for multi-worker).
    """

    def __init__(self, index_path: str | None = None):
        self.index_path = Path(index_path or settings.faiss_index_path)
        self.index_path.mkdir(parents=True, exist_ok=True)
        self._index = None        # faiss.IndexFlatIP (inner product = cosine for normalized vectors)
        self._chunks: list[Chunk] = []
        self._load()

    def _index_file(self) -> Path:
        return self.index_path / "index.faiss"

    def _meta_file(self) -> Path:
        return self.index_path / "chunks.pkl"

    def _load(self) -> None:
        """Load existing index from disk if present."""
        try:
            import faiss
            if self._index_file().exists() and self._meta_file().exists():
                self._index = faiss.read_index(str(self._index_file()))
                with open(self._meta_file(), "rb") as f:
                    self._chunks = pickle.load(f)
        except ImportError:
            pass  # FAISS not installed — will fall back to numpy search

    def _save(self) -> None:
        """Persist the FAISS index and chunk metadata to disk."""
        try:
            import faiss
            if self._index is not None:
                faiss.write_index(self._index, str(self._index_file()))
            with open(self._meta_file(), "wb") as f:
                pickle.dump(self._chunks, f)
        except ImportError:
            pass

    def add_chunks(self, chunks: list[Chunk]) -> None:
        """Embed and add a list of chunks to the store."""
        if not chunks:
            return
        texts = [c.text for c in chunks]
        embeddings = Embedder.embed(texts).astype(np.float32)

        try:
            import faiss
            dim = embeddings.shape[1]
            if self._index is None:
                self._index = faiss.IndexFlatIP(dim)
            self._index.add(embeddings)
        except ImportError:
            # Fallback: store raw embeddings in chunks
            for chunk, emb in zip(chunks, embeddings):
                chunk.metadata["_embedding"] = emb.tolist()

        self._chunks.extend(chunks)
        self._save()

    def search(self, query: str, top_k: int = 5, source_filter: str | None = None) -> list[dict]:
        """Find top-K most relevant chunks for a query."""
        if not self._chunks:
            return []

        query_emb = Embedder.embed_single(query).astype(np.float32)

        try:
            import faiss
            if self._index is not None:
                D, I = self._index.search(query_emb.reshape(1, -1), min(top_k * 2, len(self._chunks)))
                candidates = [
                    {**self._chunks[i].to_dict(), "score": float(D[0][j])}
                    for j, i in enumerate(I[0])
                    if 0 <= i < len(self._chunks)
                ]
            else:
                candidates = self._numpy_search(query_emb, top_k * 2)
        except ImportError:
            candidates = self._numpy_search(query_emb, top_k * 2)

        # Apply source filter
        if source_filter:
            candidates = [c for c in candidates if source_filter.lower() in c["source"].lower()]

        return candidates[:top_k]

    def _numpy_search(self, query_emb: np.ndarray, top_k: int) -> list[dict]:
        """Fallback: brute-force cosine similarity with numpy."""
        embeddings = []
        for chunk in self._chunks:
            emb = chunk.metadata.get("_embedding")
            if emb:
                embeddings.append(np.array(emb, dtype=np.float32))

        if not embeddings:
            return []

        matrix = np.stack(embeddings)
        scores = matrix @ query_emb
        top_indices = np.argsort(scores)[::-1][:top_k]
        return [
            {**self._chunks[i].to_dict(), "score": float(scores[i])}
            for i in top_indices
        ]

    def delete_by_source(self, source: str) -> int:
        """Remove all chunks from a specific source document."""
        original_count = len(self._chunks)
        self._chunks = [c for c in self._chunks if c.source != source]
        removed = original_count - len(self._chunks)
        if removed > 0:
            # Rebuild index without deleted chunks
            self._index = None
            if self._chunks:
                texts = [c.text for c in self._chunks]
                embeddings = Embedder.embed(texts).astype(np.float32)
                try:
                    import faiss
                    self._index = faiss.IndexFlatIP(embeddings.shape[1])
                    self._index.add(embeddings)
                except ImportError:
                    for chunk, emb in zip(self._chunks, embeddings):
                        chunk.metadata["_embedding"] = emb.tolist()
            self._save()
        return removed

    def total_chunks(self) -> int:
        return len(self._chunks)

    def list_sources(self) -> list[str]:
        return list({c.source for c in self._chunks})


# ── Global singleton ──────────────────────────────────────────────────────────
vector_store = FAISSVectorStore()
