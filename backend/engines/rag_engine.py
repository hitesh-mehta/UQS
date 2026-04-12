"""
RAG Engine — Document-grounded Q&A using vector retrieval.
"""
from __future__ import annotations

import time
from pydantic import BaseModel

from backend.core.logger import AuditEvent, AuditLogger
from backend.llm.client import llm_json
from backend.llm.context_manager import UserSession
from backend.llm.prompts.all_prompts import build_rag_prompt
from backend.vector_store.store import vector_store


class RAGResult(BaseModel):
    answer: str
    sources_used: list[str]
    confidence: str
    caveat: str | None = None
    chunks_retrieved: int
    latency_ms: float


class RAGEngine:
    """
    Retrieves relevant document chunks from the vector store
    and uses the LLM to generate a grounded, cited answer.
    """

    async def run(
        self,
        session: UserSession,
        query: str,
        session_id: str,
        audit: AuditLogger | None = None,
        top_k: int = 5,
    ) -> RAGResult:
        start = time.perf_counter()

        # ── Step 1: Retrieve top-K relevant chunks ─────────────────────────
        # Filter chunks to this user's session to prevent cross-user data leakage
        chunks = vector_store.search(
            query=query,
            top_k=top_k,
            source_filter=session_id,
        )

        if audit:
            audit.log(AuditEvent.RAG_RETRIEVAL, details={
                "query": query,
                "chunks_found": len(chunks),
            })

        # ── Step 2: Build grounded prompt + generate answer ────────────────
        system_prompt, user_message = build_rag_prompt(
            user_query=query,
            retrieved_chunks=chunks,
            rag_plus_plus=False,
        )
        raw = await llm_json(system_prompt, user_message, temperature=0.1)

        latency_ms = (time.perf_counter() - start) * 1000

        return RAGResult(
            answer=raw.get("answer", "I could not find a relevant answer in the uploaded documents."),
            sources_used=raw.get("sources_used", []),
            confidence=raw.get("confidence", "low"),
            caveat=raw.get("caveat"),
            chunks_retrieved=len(chunks),
            latency_ms=latency_ms,
        )
