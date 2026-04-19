"""
Main Query API — now powered by the LangGraph pipeline.

Endpoints:
  POST /api/query         → full response (JSON)
  GET  /api/query/stream  → streaming response (SSE, token-by-token if supported)
"""
from __future__ import annotations

import asyncio
import json
import time
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from backend.core.auth import UserContext, get_current_user
from backend.core.logger import AuditEvent, AuditLogger
from backend.core.security import get_rate_limit_string, limiter, sanitize_query
from backend.graph.pipeline import get_pipeline
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


# ── Shared pipeline helper ────────────────────────────────────────────────────

async def _run_pipeline(
    query: str,
    session_id: str,
    use_case_context: str,
    user: UserContext,
) -> tuple[dict, float]:
    """
    Run the LangGraph pipeline and return (final_response_dict, latency_ms).
    Raises HTTPException on hard failures.
    """
    t0 = time.perf_counter()
    audit = AuditLogger(user_id=user.user_id, role=user.role, session_id=session_id)
    audit.log(AuditEvent.QUERY_RECEIVED, details={"query": query})

    from backend.graph import nodes as graph_nodes

    graph_nodes.log.debug(
        "pipeline start: user_id=%s role=%s session_id=%s query_chars=%s use_case_context_chars=%s",
        user.user_id,
        user.role,
        session_id,
        len(query),
        len(use_case_context),
    )

    session = await session_store.get_or_create(
        user_id=user.user_id,
        role=user.role,
        email=user.email,
        session_id=session_id,
        use_case_context=use_case_context,
    )

    initial_state = {
        "query": query,
        "session_id": session_id,
        "session": session,
        "audit": audit,
        "user": user,
        "retry_count": 0,
        "cache_hit": False,
        "relevant": True,
        "engine_corrected": False,
        "engine_sources": [],
        "engine_key_metrics": [],
        "engine_chart": None,
        "engine_chart_type": None,
    }

    pipeline = get_pipeline()
    final_state = await pipeline.ainvoke(initial_state)

    graph_nodes.log.debug(
        "pipeline finished: keys=%s has_final_response=%s has_error=%s",
        sorted(list(final_state.keys())),
        bool(final_state.get("final_response")),
        bool(final_state.get("error")),
    )

    latency_ms = (time.perf_counter() - t0) * 1000
    response = final_state.get("final_response")

    if not response:
        raise HTTPException(status_code=500, detail="Pipeline returned no response.")

    # Inject real latency
    response["latency_ms"] = round(latency_ms, 1)

    # Update conversation history
    session.add_message("user", query)
    session.add_message("assistant", response.get("answer", ""))

    audit.log(AuditEvent.ENGINE_RESPONSE, details={
        "engine": response.get("engine"),
        "from_cache": response.get("from_cache"),
    }, latency_ms=latency_ms)

    graph_nodes.log.debug(
        "pipeline response: engine=%s query_type=%s answer_chars=%s sources=%s latency_ms=%.1f",
        response.get("engine"),
        response.get("query_type"),
        len(response.get("answer", "")),
        len(response.get("sources", [])),
        latency_ms,
    )

    return response, latency_ms


# ── POST /api/query — full JSON response ──────────────────────────────────────

@router.post("/query", response_model=QueryResponse)
@limiter.limit(get_rate_limit_string())
async def query(
    request: Request,
    body: QueryRequest,
    user: UserContext = Depends(get_current_user),
) -> QueryResponse:
    """Submit a natural language query. Returns full response when complete."""
    # Sanitize input
    clean_query, err = sanitize_query(body.query)
    if err:
        raise HTTPException(status_code=400, detail=err)

    session_id = body.session_id or str(uuid.uuid4())
    response, _ = await _run_pipeline(clean_query, session_id, body.use_case_context, user)
    return QueryResponse(**response)


# ── GET /api/query/stream — SSE streaming ────────────────────────────────────

@router.get("/query/stream")
@limiter.limit(get_rate_limit_string())
async def query_stream(
    request: Request,
    query: str,
    session_id: str | None = None,
    use_case_context: str = "enterprise data analytics platform",
    user: UserContext = Depends(get_current_user),
) -> StreamingResponse:
    """
    Submit a query and receive a streaming SSE response.

    SSE event format:
      event: token          — individual answer word
      event: metadata       — JSON with engine, sources, metrics, chart
      event: done           — signals stream end
      event: error          — signals an error
    """
    clean_query, err = sanitize_query(query)
    if err:
        raise HTTPException(status_code=400, detail=err)

    sid = session_id or str(uuid.uuid4())

    async def event_generator():
        try:
            # Run the full pipeline first (LangGraph doesn't natively stream tokens
            # from arbitrary LLM providers, so we do word-level streaming of the answer)
            response, latency_ms = await _run_pipeline(
                clean_query, sid, use_case_context, user
            )
            answer: str = response.get("answer", "")

            # Stream words with small delay for visible effect
            words = answer.split()
            for i, word in enumerate(words):
                # Check if client disconnected
                if await request.is_disconnected():
                    break
                chunk = word + (" " if i < len(words) - 1 else "")
                yield f"event: token\ndata: {json.dumps({'token': chunk})}\n\n"
                await asyncio.sleep(0.01)  # ~100 words/sec streaming

            # Send metadata after full answer streamed
            meta = {
                "engine": response.get("engine"),
                "query_type": response.get("query_type"),
                "sources": response.get("sources", []),
                "key_metrics": response.get("key_metrics", []),
                "chart": response.get("chart"),
                "chart_type": response.get("chart_type"),
                "from_cache": response.get("from_cache", False),
                "corrected": response.get("corrected", False),
                "latency_ms": latency_ms,
                "model_version": response.get("model_version"),
                "session_id": sid,
            }
            yield f"event: metadata\ndata: {json.dumps(meta)}\n\n"
            yield "event: done\ndata: {}\n\n"

        except HTTPException as e:
            yield f"event: error\ndata: {json.dumps({'detail': e.detail})}\n\n"
        except Exception as e:
            yield f"event: error\ndata: {json.dumps({'detail': str(e)})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        },
    )
