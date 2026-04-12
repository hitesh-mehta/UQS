"""
UQS LangGraph State Definition.

UQSState is the single TypedDict that flows through every node of the
LangGraph StateGraph. Nodes receive the full state and return a partial
dict to update only what they changed — LangGraph merges automatically.
"""
from __future__ import annotations

from typing import Any, Optional
from typing_extensions import TypedDict


class UQSState(TypedDict, total=False):
    # ── Inputs (set at graph entry) ───────────────────────────────────────────
    query: str                         # Raw natural-language question
    session_id: str                    # Per-user session UUID
    session: Any                       # UserSession object (schema, history)
    audit: Any                         # AuditLogger instance
    user: Any                          # UserContext from JWT

    # ── Classification result (set by node_classify) ─────────────────────────
    query_type: str                    # sql | analytical | predictive | rag | rag++ | irrelevant
    query_sub_type: Optional[str]      # trend_analysis | causal_diagnostic | etc.
    relevant: bool                     # False → short-circuit with polite rejection
    polite_rejection: Optional[str]    # Message when irrelevant=True

    # ── Cache (set by node_check_cache) ──────────────────────────────────────
    cache_hit: bool
    cache_answer: Optional[str]
    cache_source: Optional[str]

    # ── Engine output (set by engine nodes) ──────────────────────────────────
    engine_answer: str                 # Plain-English narrative
    engine_sources: list[str]
    engine_key_metrics: list[dict]
    engine_chart: Optional[dict]
    engine_chart_type: Optional[str]
    engine_corrected: bool             # SQL self-corrected flag
    engine_model_version: Optional[int]  # Predictive engine model version

    # ── Error handling ────────────────────────────────────────────────────────
    error: Optional[str]              # Last error message
    retry_count: int                  # Incremented on retryable failures

    # ── Final assembled response (set by node_format) ────────────────────────
    final_response: Optional[dict]    # Serialized QueryResponse
