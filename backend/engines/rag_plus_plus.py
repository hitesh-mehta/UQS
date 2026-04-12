"""
RAG++ Engine — Hybrid DB data + Document context merging.
Fetches live DB context via the SQL Engine AND document chunks via the RAG Engine,
then merges them for a richer, dual-source answer.
"""
from __future__ import annotations

import time
from pydantic import BaseModel

from backend.core.logger import AuditEvent, AuditLogger
from backend.engines.rag_engine import RAGEngine, RAGResult
from backend.engines.sql_engine import SQLEngine
from backend.llm.client import llm_json
from backend.llm.context_manager import UserSession
from backend.llm.prompts.all_prompts import build_rag_prompt
from backend.vector_store.store import vector_store


class RagPlusPlusResult(BaseModel):
    answer: str
    sources_used: list[str]
    db_context_summary: str
    doc_context_summary: str
    confidence: str
    latency_ms: float


class RagPlusPlusEngine:
    """
    Combines:
      1. SQL Engine  → fetches relevant live DB data
      2. RAG Engine  → retrieves document chunks
      3. Context merger → LLM synthesizes both into a unified answer
    """

    def __init__(self):
        self._sql_engine = SQLEngine()
        self._rag_engine = RAGEngine()

    async def run(
        self,
        session: UserSession,
        query: str,
        session_id: str,
        audit: AuditLogger | None = None,
        top_k: int = 5,
    ) -> RagPlusPlusResult:
        start = time.perf_counter()

        # ── Parallel: fetch DB data AND document chunks ──────────────────
        import asyncio
        db_task = self._fetch_db_context(session, query, audit)
        doc_task = self._fetch_doc_chunks(query, session_id, top_k)

        db_context, doc_chunks = await asyncio.gather(db_task, doc_task, return_exceptions=True)

        # Handle errors gracefully
        if isinstance(db_context, Exception):
            db_context_str = f"(DB fetch failed: {str(db_context)})"
            db_sources = []
        else:
            db_context_str, db_sources = db_context

        if isinstance(doc_chunks, Exception):
            doc_chunks = []

        # ── Merge contexts and generate answer ────────────────────────────
        system_prompt, user_message = build_rag_prompt(
            user_query=query,
            retrieved_chunks=doc_chunks,
            rag_plus_plus=True,
            db_context=db_context_str,
        )
        raw = await llm_json(system_prompt, user_message, temperature=0.1)

        all_sources = db_sources + raw.get("sources_used", [])
        latency_ms = (time.perf_counter() - start) * 1000

        if audit:
            audit.log(AuditEvent.ENGINE_RESPONSE, details={
                "engine": "rag++",
                "doc_chunks": len(doc_chunks),
                "db_sources": db_sources,
            }, latency_ms=latency_ms)

        return RagPlusPlusResult(
            answer=raw.get("answer", "Unable to generate a combined answer."),
            sources_used=list(set(all_sources)),
            db_context_summary=db_context_str[:500] if isinstance(db_context_str, str) else "",
            doc_context_summary=f"{len(doc_chunks)} document chunks retrieved",
            confidence=raw.get("confidence", "medium"),
            latency_ms=latency_ms,
        )

    async def _fetch_db_context(self, session: UserSession, query: str, audit: AuditLogger | None) -> tuple[str, list[str]]:
        """Run SQL engine to get relevant DB data."""
        try:
            sql_result = await self._sql_engine.run(session, query, audit)
            # Serialize top rows as context string
            if sql_result.rows:
                headers = sql_result.columns
                rows_str = "\n".join(
                    " | ".join(str(row.get(h, "")) for h in headers)
                    for row in sql_result.rows[:20]
                )
                context = f"DB Query Result ({sql_result.row_count} rows):\n{' | '.join(headers)}\n{rows_str}"
            else:
                context = "DB query returned no results."
            return context, sql_result.sources
        except Exception as e:
            raise

    async def _fetch_doc_chunks(self, query: str, session_id: str, top_k: int) -> list[dict]:
        """Retrieve document chunks from vector store."""
        return vector_store.search(query=query, top_k=top_k, source_filter=session_id)
