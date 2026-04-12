"""
Document Ingestion Pipeline for RAG.
Handles PDF, DOCX, TXT ingestion:
  - Reads raw text from document
  - Chunks the text with overlap for context preservation
  - Adds chunks to the vector store
"""
from __future__ import annotations

import io
import os
from pathlib import Path
from typing import Optional

from backend.vector_store.store import Chunk, vector_store


# ── Chunking ──────────────────────────────────────────────────────────────────

def chunk_text(
    text: str,
    chunk_size: int = 500,
    overlap: int = 100,
) -> list[str]:
    """
    Split text into overlapping chunks.
    Overlap ensures context is preserved across chunk boundaries.
    """
    if not text.strip():
        return []

    words = text.split()
    chunks = []
    start = 0
    while start < len(words):
        end = min(start + chunk_size, len(words))
        chunk = " ".join(words[start:end])
        if chunk.strip():
            chunks.append(chunk)
        if end >= len(words):
            break
        start += chunk_size - overlap

    return chunks


# ── PDF Reader ────────────────────────────────────────────────────────────────

def _read_pdf(file_bytes: bytes) -> list[tuple[int, str]]:
    """Returns list of (page_number, page_text) tuples."""
    try:
        import pymupdf  # PyMuPDF (fitz renamed)
        doc = pymupdf.open(stream=file_bytes, filetype="pdf")
        pages = []
        for i, page in enumerate(doc, 1):
            text = page.get_text("text")
            if text.strip():
                pages.append((i, text))
        doc.close()
        return pages
    except ImportError:
        try:
            import pypdf
            reader = pypdf.PdfReader(io.BytesIO(file_bytes))
            return [
                (i + 1, page.extract_text() or "")
                for i, page in enumerate(reader.pages)
                if page.extract_text()
            ]
        except ImportError:
            raise RuntimeError(
                "Install a PDF library: pip install pymupdf  OR  pip install pypdf"
            )


# ── DOCX Reader ───────────────────────────────────────────────────────────────

def _read_docx(file_bytes: bytes) -> str:
    """Extract full text from DOCX file."""
    try:
        import docx
        doc = docx.Document(io.BytesIO(file_bytes))
        return "\n".join(para.text for para in doc.paragraphs)
    except ImportError:
        raise RuntimeError("Install 'python-docx': pip install python-docx")


# ── Main Ingestion ────────────────────────────────────────────────────────────

async def ingest_document(
    file_bytes: bytes,
    filename: str,
    user_id: str,
    session_id: str,
    chunk_size: int = 500,
    overlap: int = 100,
) -> dict:
    """
    Ingest a document into the vector store.
    Supports: PDF, DOCX, TXT, MD

    Returns:
        dict with ingestion summary (chunks_added, source_name, etc.)
    """
    ext = Path(filename).suffix.lower()
    source_name = f"{filename}:{session_id}"  # Scope to session to avoid cross-user leakage

    # ── Parse document ─────────────────────────────────────────────────────
    chunks_with_pages: list[tuple[Optional[int], str]] = []

    if ext == ".pdf":
        pages = _read_pdf(file_bytes)
        for page_num, page_text in pages:
            for chunk_text_str in chunk_text(page_text, chunk_size, overlap):
                chunks_with_pages.append((page_num, chunk_text_str))

    elif ext in (".docx", ".doc"):
        full_text = _read_docx(file_bytes)
        for chunk_text_str in chunk_text(full_text, chunk_size, overlap):
            chunks_with_pages.append((None, chunk_text_str))

    elif ext in (".txt", ".md", ".csv"):
        full_text = file_bytes.decode("utf-8", errors="ignore")
        for chunk_text_str in chunk_text(full_text, chunk_size, overlap):
            chunks_with_pages.append((None, chunk_text_str))

    else:
        raise ValueError(f"Unsupported file type: '{ext}'. Supported: PDF, DOCX, TXT, MD")

    if not chunks_with_pages:
        raise ValueError(f"No text could be extracted from '{filename}'.")

    # ── Create Chunk objects and add to vector store ────────────────────────
    chunk_objects = [
        Chunk(
            text=text,
            source=source_name,
            page=page,
            chunk_index=i,
            metadata={"user_id": user_id, "filename": filename, "session_id": session_id},
        )
        for i, (page, text) in enumerate(chunks_with_pages)
    ]

    vector_store.add_chunks(chunk_objects)

    return {
        "filename": filename,
        "source_key": source_name,
        "chunks_added": len(chunk_objects),
        "pages_processed": len({p for p, _ in chunks_with_pages if p is not None}),
        "total_characters": sum(len(t) for _, t in chunks_with_pages),
    }
