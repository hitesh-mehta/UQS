"""
Document Upload API — POST /api/documents
Handles file uploads for RAG ingestion and returns ingestion status.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from backend.core.auth import UserContext, get_current_user
from backend.core.logger import AuditEvent, AuditLogger
from backend.vector_store.ingestion import ingest_document
from backend.vector_store.store import vector_store

router = APIRouter(prefix="/api/documents", tags=["documents"])


class IngestionResponse(BaseModel):
    filename: str
    source_key: str
    chunks_added: int
    pages_processed: int
    total_characters: int
    message: str


class DocumentListResponse(BaseModel):
    sources: list[str]
    total_chunks: int


@router.post("/upload", response_model=IngestionResponse)
async def upload_document(
    file: UploadFile = File(...),
    session_id: str = Form(...),
    user: UserContext = Depends(get_current_user),
) -> IngestionResponse:
    """
    Upload a document (PDF, DOCX, TXT, MD) for RAG ingestion.
    The document is chunked, embedded, and added to the vector store.
    """
    audit = AuditLogger(user_id=user.user_id, role=user.role, session_id=session_id)

    # Validate file type
    allowed_extensions = {".pdf", ".docx", ".doc", ".txt", ".md"}
    filename = file.filename or "unknown"
    ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"File type '{ext}' not supported. Allowed: {', '.join(allowed_extensions)}",
        )

    # Read file bytes
    file_bytes = await file.read()
    if len(file_bytes) > 50 * 1024 * 1024:  # 50MB limit
        raise HTTPException(status_code=413, detail="File too large. Maximum size: 50MB")

    try:
        result = await ingest_document(
            file_bytes=file_bytes,
            filename=filename,
            user_id=user.user_id,
            session_id=session_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))

    audit.log(AuditEvent.RAG_INGESTION, details=result)

    return IngestionResponse(
        **result,
        message=f"Successfully ingested {result['chunks_added']} chunks from '{filename}'. You can now ask questions about this document.",
    )


@router.get("/list", response_model=DocumentListResponse)
async def list_documents(
    user: UserContext = Depends(get_current_user),
) -> DocumentListResponse:
    """List all documents currently in the vector store."""
    return DocumentListResponse(
        sources=vector_store.list_sources(),
        total_chunks=vector_store.total_chunks(),
    )


@router.delete("/{source_key}")
async def delete_document(
    source_key: str,
    user: UserContext = Depends(get_current_user),
) -> dict:
    """Remove a document from the vector store by its source key."""
    removed = vector_store.delete_by_source(source_key)
    return {"removed_chunks": removed, "source_key": source_key}
