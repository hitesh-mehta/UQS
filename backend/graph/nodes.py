"""
LangGraph Node Functions for the UQS pipeline.

Each node is an async function:
    async def node_*(state: UQSState) -> dict

Nodes return ONLY the keys they changed — LangGraph merges them into state.
All exceptions are caught and pushed into state["error"] for graceful degradation.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from backend.cache.cache_query import check_cache
from backend.core.logger import AuditEvent
from backend.engines.analytical_engine import AnalyticalEngine
from backend.engines.classifier import QueryClassifier
from backend.engines.predictive_engine import PredictiveEngine
from backend.engines.rag_engine import RAGEngine
from backend.engines.rag_plus_plus import RagPlusPlusEngine
from backend.engines.sql_engine import SQLEngine
from backend.graph.state import UQSState

log = logging.getLogger("uqs.graph")

# ── Engine singletons (shared, thread-safe) ───────────────────────────────────
_classifier = QueryClassifier()
_sql = SQLEngine()
_analytical = AnalyticalEngine()
_predictive = PredictiveEngine()
_rag = RAGEngine()
_rag_plus = RagPlusPlusEngine()

# ── Max seconds any single node may run ───────────────────────────────────────
NODE_TIMEOUT = 28.0


# ─────────────────────────────────────────────────────────────────────────────
# NODE 1: Classify the incoming query
# ─────────────────────────────────────────────────────────────────────────────
async def node_classify(state: UQSState) -> dict:
    """Classify the query into engine type using LLM."""
    try:
        log.debug(
            "node_classify start: session_id=%s query_chars=%s has_session=%s has_audit=%s",
            state.get("session_id"),
            len(state.get("query", "")),
            bool(state.get("session")),
            bool(state.get("audit")),
        )
        result = await asyncio.wait_for(
            _classifier.classify(state["session"], state["query"], state.get("audit")),
            timeout=NODE_TIMEOUT,
        )
        log.debug(
            "node_classify result: relevant=%s type=%s sub_type=%s reasoning_chars=%s",
            result.relevant,
            result.type,
            result.sub_type,
            len(result.reasoning or ""),
        )
        update = {
            "query_type": result.type,
            "query_sub_type": result.sub_type,
            "relevant": result.relevant,
            "polite_rejection": result.polite_rejection if not result.relevant else None,
            "error": None,
        }
        if state.get("audit"):
            state["audit"].log(AuditEvent.ENGINE_ROUTED, details={
                "query_type": result.type,
                "relevant": result.relevant,
            })
        return update
    except asyncio.TimeoutError:
        return {"error": "Classification timed out.", "relevant": False, "query_type": "irrelevant"}
    except Exception as exc:
        log.exception("node_classify failed")
        return {"error": str(exc), "relevant": False, "query_type": "irrelevant"}


# ─────────────────────────────────────────────────────────────────────────────
# NODE 2: Check the cache
# ─────────────────────────────────────────────────────────────────────────────
async def node_check_cache(state: UQSState) -> dict:
    """Check if the query can be answered from a pre-generated cached report."""
    try:
        log.debug(
            "node_check_cache start: query_type=%s query_chars=%s",
            state.get("query_type"),
            len(state.get("query", "")),
        )
        result = await asyncio.wait_for(
            check_cache(state["query"]),
            timeout=5.0,  # Cache check should be very fast
        )
        if result.cache_hit:
            log.debug("node_check_cache hit: matching_report=%s", result.matching_report)
            if state.get("audit"):
                state["audit"].log(AuditEvent.CACHE_HIT, details={
                    "matching_report": result.matching_report
                })
            return {
                "cache_hit": True,
                "cache_answer": result.answer_from_cache,
                "cache_source": result.matching_report,
                "error": None,
            }
        log.debug("node_check_cache miss")
        if state.get("audit"):
            state["audit"].log(AuditEvent.CACHE_MISS, details={})
        return {"cache_hit": False}
    except Exception as exc:
        log.warning(f"node_check_cache failed (non-fatal): {exc}")
        return {"cache_hit": False}  # Cache miss is safe to ignore


# ─────────────────────────────────────────────────────────────────────────────
# NODE 3: SQL Engine
# ─────────────────────────────────────────────────────────────────────────────
async def node_sql(state: UQSState) -> dict:
    """Run NL→SQL pipeline with DIN-SQL patterns and self-correction loop."""
    try:
        result = await asyncio.wait_for(
            _sql.run(state["session"], state["query"], state.get("audit")),
            timeout=NODE_TIMEOUT,
        )
        chart = None
        chart_type = None
        if result.rows and result.columns:
            chart = {"columns": result.columns, "rows": result.rows[:50]}
            chart_type = "table"
        return {
            "engine_answer": result.explanation,
            "engine_sources": result.sources,
            "engine_key_metrics": [],
            "engine_chart": chart,
            "engine_chart_type": chart_type,
            "engine_corrected": result.corrected,
            "engine_model_version": None,
            "error": None,
        }
    except Exception as exc:
        log.exception("node_sql failed")
        return {"error": str(exc), "engine_answer": "", "engine_sources": []}


# ─────────────────────────────────────────────────────────────────────────────
# NODE 4: Analytical Engine
# ─────────────────────────────────────────────────────────────────────────────
async def node_analytical(state: UQSState) -> dict:
    """Run the algorithm-brain analytical pipeline."""
    try:
        result = await asyncio.wait_for(
            _analytical.run(
                state["session"],
                state["query"],
                sub_type=state.get("query_sub_type", ""),
                audit=state.get("audit"),
            ),
            timeout=NODE_TIMEOUT,
        )
        narrative = (result.headline + "\n\n" + result.narrative) if result.headline else result.narrative
        return {
            "engine_answer": narrative,
            "engine_sources": result.sources,
            "engine_key_metrics": result.key_metrics,
            "engine_chart": result.chart_data,
            "engine_chart_type": result.chart_type,
            "engine_corrected": False,
            "engine_model_version": None,
            "error": None,
        }
    except Exception as exc:
        log.exception("node_analytical failed")
        return {"error": str(exc), "engine_answer": "", "engine_sources": []}


# ─────────────────────────────────────────────────────────────────────────────
# NODE 5: Predictive Engine
# ─────────────────────────────────────────────────────────────────────────────
async def node_predictive(state: UQSState) -> dict:
    """Run ML inference (XGBoost / RF / LightGBM / Prophet)."""
    try:
        result = await asyncio.wait_for(
            _predictive.run(state["session"], state["query"], state.get("audit")),
            timeout=NODE_TIMEOUT,
        )
        return {
            "engine_answer": result.narrative,
            "engine_sources": result.sources,
            "engine_key_metrics": [],
            "engine_chart": {"predictions": [p.model_dump() for p in result.predictions]},
            "engine_chart_type": "predictions",
            "engine_corrected": False,
            "engine_model_version": result.model_version,
            "error": None,
        }
    except Exception as exc:
        log.exception("node_predictive failed")
        return {"error": str(exc), "engine_answer": "", "engine_sources": []}


# ─────────────────────────────────────────────────────────────────────────────
# NODE 6: RAG Engine
# ─────────────────────────────────────────────────────────────────────────────
async def node_rag(state: UQSState) -> dict:
    """Document Q&A via FAISS vector retrieval."""
    try:
        result = await asyncio.wait_for(
            _rag.run(state["session"], state["query"], state["session_id"], state.get("audit")),
            timeout=NODE_TIMEOUT,
        )
        return {
            "engine_answer": result.answer,
            "engine_sources": result.sources_used,
            "engine_key_metrics": [],
            "engine_chart": None,
            "engine_chart_type": None,
            "engine_corrected": False,
            "engine_model_version": None,
            "error": None,
        }
    except Exception as exc:
        log.exception("node_rag failed")
        return {"error": str(exc), "engine_answer": "", "engine_sources": []}


# ─────────────────────────────────────────────────────────────────────────────
# NODE 7: RAG++ Engine
# ─────────────────────────────────────────────────────────────────────────────
async def node_rag_plus_plus(state: UQSState) -> dict:
    """Hybrid DB + document context merging."""
    try:
        result = await asyncio.wait_for(
            _rag_plus.run(state["session"], state["query"], state["session_id"], state.get("audit")),
            timeout=NODE_TIMEOUT,
        )
        return {
            "engine_answer": result.answer,
            "engine_sources": result.sources_used,
            "engine_key_metrics": [],
            "engine_chart": None,
            "engine_chart_type": None,
            "engine_corrected": False,
            "engine_model_version": None,
            "error": None,
        }
    except Exception as exc:
        log.exception("node_rag_plus_plus failed")
        return {"error": str(exc), "engine_answer": "", "engine_sources": []}


# ─────────────────────────────────────────────────────────────────────────────
# NODE 8: Format final response
# ─────────────────────────────────────────────────────────────────────────────
async def node_format_response(state: UQSState) -> dict:
    """Assemble the final QueryResponse dict from engine outputs."""
    import time

    # If cache hit — use cache answer
    if state.get("cache_hit") and state.get("cache_answer"):
        log.debug("node_format_response using cache answer")
        response = {
            "answer": state["cache_answer"],
            "engine": "cache",
            "query_type": state.get("query_type", "sql"),
            "sources": [state.get("cache_source", "cache")],
            "key_metrics": [],
            "chart": None,
            "chart_type": None,
            "from_cache": True,
            "corrected": False,
            "latency_ms": 0.0,
            "model_version": None,
            "session_id": state["session_id"],
        }
        return {"final_response": response}

    # If irrelevant or error with no answer
    if not state.get("relevant", True):
        log.debug("node_format_response using rejection path")
        response = {
            "answer": state.get("polite_rejection", "I can only answer questions about your data."),
            "engine": "classifier",
            "query_type": "irrelevant",
            "sources": [],
            "key_metrics": [],
            "chart": None,
            "chart_type": None,
            "from_cache": False,
            "corrected": False,
            "latency_ms": 0.0,
            "model_version": None,
            "session_id": state["session_id"],
        }
        return {"final_response": response}

    # Engine result with error fallback
    answer = state.get("engine_answer", "")
    if not answer and state.get("error"):
        answer = f"I encountered an issue processing your request: {state['error']}"

    log.debug(
        "node_format_response engine path: query_type=%s sub_type=%s answer_chars=%s sources=%s",
        state.get("query_type"),
        state.get("query_sub_type"),
        len(answer),
        len(state.get("engine_sources", [])),
    )
    response = {
        "answer": answer,
        "engine": state.get("query_type", "sql"),
        "query_type": state.get("query_sub_type") or state.get("query_type", "sql"),
        "sources": state.get("engine_sources", []),
        "key_metrics": state.get("engine_key_metrics", []),
        "chart": state.get("engine_chart"),
        "chart_type": state.get("engine_chart_type"),
        "from_cache": False,
        "corrected": state.get("engine_corrected", False),
        "latency_ms": 0.0,
        "model_version": state.get("engine_model_version"),
        "session_id": state["session_id"],
    }
    return {"final_response": response}


# ─────────────────────────────────────────────────────────────────────────────
# CONDITIONAL EDGE FUNCTIONS
# ─────────────────────────────────────────────────────────────────────────────
def edge_after_classify(state: UQSState) -> str:
    """Route after classification."""
    if not state.get("relevant", True):
        return "format_response"
    if state.get("error"):
        return "format_response"
    return "check_cache"


def edge_after_cache(state: UQSState) -> str:
    """Route after cache check."""
    if state.get("cache_hit"):
        return "format_response"
    qt = state.get("query_type", "sql")
    engine_map = {
        "sql": "sql",
        "analytical": "analytical",
        "predictive": "predictive",
        "rag": "rag",
        "rag++": "rag_plus_plus",
    }
    return engine_map.get(qt, "sql")
