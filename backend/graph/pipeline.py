"""
UQS LangGraph Pipeline.

Builds and compiles the StateGraph that orchestrates the entire
query-answering pipeline. The compiled graph is a singleton reused
across all requests.

Graph topology:
    START
      ↓
    classify  ──[irrelevant/error]──────────────────────────→ format_response
      ↓ [relevant]
    check_cache ──[cache_hit]──────────────────────────────→ format_response
      ↓ [cache_miss]
      ├── sql ──────────────────────────────────────────────→ format_response
      ├── analytical ────────────────────────────────────────→ format_response
      ├── predictive ────────────────────────────────────────→ format_response
      ├── rag ───────────────────────────────────────────────→ format_response
      └── rag_plus_plus ─────────────────────────────────────→ format_response
                                                                      ↓
                                                                     END
"""
from __future__ import annotations

import logging
from functools import lru_cache

from langgraph.graph import END, START, StateGraph

from backend.graph.nodes import (
    edge_after_cache,
    edge_after_classify,
    node_analytical,
    node_check_cache,
    node_classify,
    node_format_response,
    node_predictive,
    node_rag,
    node_rag_plus_plus,
    node_sql,
)
from backend.graph.state import UQSState

log = logging.getLogger("uqs.graph")


def build_graph():
    """Build and compile the UQS StateGraph."""
    g = StateGraph(UQSState)

    # ── Add nodes ─────────────────────────────────────────────────────────────
    g.add_node("classify", node_classify)
    g.add_node("check_cache", node_check_cache)
    g.add_node("sql", node_sql)
    g.add_node("analytical", node_analytical)
    g.add_node("predictive", node_predictive)
    g.add_node("rag", node_rag)
    g.add_node("rag_plus_plus", node_rag_plus_plus)
    g.add_node("format_response", node_format_response)

    # ── Entry ─────────────────────────────────────────────────────────────────
    g.add_edge(START, "classify")

    # ── After classify: irrelevant/error → format, else → cache check ─────────
    g.add_conditional_edges(
        "classify",
        edge_after_classify,
        {
            "check_cache": "check_cache",
            "format_response": "format_response",
        },
    )

    # ── After cache: hit → format, miss → appropriate engine ──────────────────
    g.add_conditional_edges(
        "check_cache",
        edge_after_cache,
        {
            "format_response": "format_response",
            "sql": "sql",
            "analytical": "analytical",
            "predictive": "predictive",
            "rag": "rag",
            "rag_plus_plus": "rag_plus_plus",
        },
    )

    # ── All engines lead to format_response ───────────────────────────────────
    for engine_node in ("sql", "analytical", "predictive", "rag", "rag_plus_plus"):
        g.add_edge(engine_node, "format_response")

    # ── format_response → END ─────────────────────────────────────────────────
    g.add_edge("format_response", END)

    compiled = g.compile()
    log.info("UQS LangGraph pipeline compiled successfully.")
    return compiled


@lru_cache(maxsize=1)
def get_pipeline():
    """Return the compiled LangGraph pipeline singleton."""
    return build_graph()


# Convenience alias
pipeline = get_pipeline()
