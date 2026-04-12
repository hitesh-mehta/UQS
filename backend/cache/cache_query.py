"""
LLM-assisted cache hit detection.
Checks if an incoming query can be answered from pre-generated cached reports,
avoiding DB queries and expensive LLM pipelines entirely.
"""
from __future__ import annotations

from pydantic import BaseModel

from backend.cache.cache_manager import cache_manager
from backend.llm.client import llm_json
from backend.llm.prompts.all_prompts import build_cache_check_prompt


class CacheCheckResult(BaseModel):
    cache_hit: bool
    matching_report: str | None = None
    reasoning: str
    answer_from_cache: str | None = None


async def check_cache(query: str) -> CacheCheckResult:
    """
    Check whether any cached report can answer the given query.
    Uses the LLM to perform semantic matching against report summaries.
    Returns a CacheCheckResult with the answer if hit, or cache_miss if not.
    """
    summaries = cache_manager.get_all_summaries()

    if not summaries:
        return CacheCheckResult(
            cache_hit=False,
            reasoning="No cached reports available yet.",
        )

    system_prompt, user_message = build_cache_check_prompt(
        user_query=query,
        cache_summaries=summaries,
    )

    raw = await llm_json(system_prompt, user_message, temperature=0.0)

    if raw.get("cache_hit", False):
        return CacheCheckResult(
            cache_hit=True,
            matching_report=raw.get("matching_report"),
            reasoning=raw.get("reasoning", ""),
            answer_from_cache=raw.get("answer_from_cache", ""),
        )

    return CacheCheckResult(
        cache_hit=False,
        reasoning=raw.get("reasoning", "Cache miss."),
    )
