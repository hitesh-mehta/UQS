"""
Main Query API — POST /api/query
The central orchestration endpoint that routes through the full UQS pipeline.
"""
from __future__ import annotations

import time
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from backend.cache.cache_query import check_cache
from backend.core.auth import UserContext, get_current_user
from backend.core.logger import AuditEvent, AuditLogger
from backend.engines.analytical_engine import AnalyticalEngine
from backend.engines.classifier import QueryClassifier
from backend.engines.predictive_engine import PredictiveEngine
from backend.engines.rag_engine import RAGEngine
from backend.engines.rag_plus_plus import RagPlusPlusEngine
from backend.engines.sql_engine import SQLEngine
from backend.llm.context_manager import session_store

router = APIRouter(prefix="/api", tags=["query"])

# ── Request / Response Models ─────────────────────────────────────────────────

class QueryRequest(BaseModel):
    query: str
    session_id: str | None = None
    use_case_context: str = "enterprise data analytics platform"


class QueryResponse(BaseModel):
    answer: str
    engine: str
    query_type: str
    sources: list[str]
    key_metrics: list[dict] = []
    chart: dict | None = None
    chart_type: str | None = None
    from_cache: bool = False
    corrected: bool = False
    latency_ms: float
    model_version: int | None = None
    session_id: str


# ── Engine singletons ─────────────────────────────────────────────────────────
_classifier = QueryClassifier()
_sql_engine = SQLEngine()
_analytical_engine = AnalyticalEngine()
_predictive_engine = PredictiveEngine()
_rag_engine = RAGEngine()
_rag_plus_plus_engine = RagPlusPlusEngine()


# ── Main Query Endpoint ───────────────────────────────────────────────────────

@router.post("/query", response_model=QueryResponse)
async def query(
    request: QueryRequest,
    user: UserContext = Depends(get_current_user),
) -> QueryResponse:
    start = time.perf_counter()
    session_id = request.session_id or str(uuid.uuid4())
    audit = AuditLogger(user_id=user.user_id, role=user.role, session_id=session_id)

    audit.log(AuditEvent.QUERY_RECEIVED, details={"query": request.query})

    # ── Step 1: Get or create user session (loads role-scoped schema) ──────
    session = await session_store.get_or_create(
        user_id=user.user_id,
        role=user.role,
        email=user.email,
        session_id=session_id,
        use_case_context=request.use_case_context,
    )

    # ── Step 2: Classify the query ──────────────────────────────────────────
    classification = await _classifier.classify(session, request.query, audit)

    if not classification.relevant:
        session.add_message("user", request.query)
        session.add_message("assistant", classification.polite_rejection)
        latency_ms = (time.perf_counter() - start) * 1000
        return QueryResponse(
            answer=classification.polite_rejection,
            engine="classifier",
            query_type="irrelevant",
            sources=[],
            from_cache=False,
            latency_ms=latency_ms,
            session_id=session_id,
        )

    # ── Step 3: Check cache ─────────────────────────────────────────────────
    cache_result = await check_cache(request.query)
    if cache_result.cache_hit and cache_result.answer_from_cache:
        audit.log(AuditEvent.CACHE_HIT, details={"matching_report": cache_result.matching_report})
        latency_ms = (time.perf_counter() - start) * 1000
        session.add_message("user", request.query)
        session.add_message("assistant", cache_result.answer_from_cache)
        return QueryResponse(
            answer=cache_result.answer_from_cache,
            engine="cache",
            query_type=classification.type,
            sources=[cache_result.matching_report or "cache"],
            from_cache=True,
            latency_ms=latency_ms,
            session_id=session_id,
        )

    audit.log(AuditEvent.CACHE_MISS, details={"query_type": classification.type})
    audit.log(AuditEvent.ENGINE_ROUTED, details={"engine": classification.type})

    # ── Step 4: Route to specialized engine ────────────────────────────────
    query_type = classification.type
    answer = ""
    sources: list[str] = []
    key_metrics: list[dict] = []
    chart: dict | None = None
    chart_type: str | None = None
    corrected = False
    model_version: int | None = None

    if query_type == "sql":
        result = await _sql_engine.run(session, request.query, audit)
        answer = result.explanation
        sources = result.sources
        corrected = result.corrected
        # Build chart data from rows if possible
        if result.rows and result.columns:
            chart = {"columns": result.columns, "rows": result.rows[:50]}
            chart_type = "table"

    elif query_type == "analytical":
        result = await _analytical_engine.run(
            session, request.query, sub_type=classification.sub_type, audit=audit
        )
        answer = result.headline + "\n\n" + result.narrative if result.headline else result.narrative
        sources = result.sources
        key_metrics = result.key_metrics
        chart = result.chart_data
        chart_type = result.chart_type

    elif query_type == "predictive":
        result = await _predictive_engine.run(session, request.query, audit)
        answer = result.narrative
        sources = result.sources
        model_version = result.model_version
        chart = {"predictions": [p.model_dump() for p in result.predictions]}
        chart_type = "predictions"

    elif query_type == "rag":
        result = await _rag_engine.run(session, request.query, session_id, audit)
        answer = result.answer
        sources = result.sources_used

    elif query_type == "rag++":
        result = await _rag_plus_plus_engine.run(session, request.query, session_id, audit)
        answer = result.answer
        sources = result.sources_used

    else:
        raise HTTPException(status_code=400, detail=f"Unknown query type: {query_type}")

    # ── Step 5: Update conversation history ────────────────────────────────
    session.add_message("user", request.query)
    session.add_message("assistant", answer)

    latency_ms = (time.perf_counter() - start) * 1000

    audit.log(AuditEvent.ENGINE_RESPONSE, details={
        "engine": query_type,
        "answer_length": len(answer),
    }, latency_ms=latency_ms)

    return QueryResponse(
        answer=answer,
        engine=query_type,
        query_type=classification.sub_type or query_type,
        sources=sources,
        key_metrics=key_metrics,
        chart=chart,
        chart_type=chart_type,
        from_cache=False,
        corrected=corrected,
        latency_ms=latency_ms,
        model_version=model_version,
        session_id=session_id,
    )
