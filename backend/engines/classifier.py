"""
Query Classification Engine.
Uses an LLM to determine if a query is relevant and routes it to the correct engine.

Taxonomy:
  - sql         → Direct data retrieval / aggregation
  - analytical  → Trend, causal, what-if, comparative, time-series
  - predictive  → Forecasting, clustering, anomaly detection
  - rag         → Document-grounded Q&A
  - rag++       → DB data + document hybrid
  - irrelevant  → Out of scope
"""
from __future__ import annotations

import logging

from pydantic import BaseModel

from backend.core.logger import AuditEvent, AuditLogger
from backend.llm.client import llm_json
from backend.llm.context_manager import UserSession
from backend.llm.prompts.all_prompts import build_classifier_prompt

log = logging.getLogger("uqs.classifier")


# ── Result Model ──────────────────────────────────────────────────────────────

class ClassificationResult(BaseModel):
    relevant: bool
    type: str      # sql | analytical | predictive | rag | rag++ | irrelevant
    sub_type: str | None = ""
    reasoning: str = ""
    polite_rejection: str | None = None   # Set when irrelevant=True

REJECTION_RESPONSES = [
    "That question falls outside the scope of this platform. I can help you analyze your business data — try asking about sales, customers, performance metrics, or predictions.",
    "I'm specialized in data analytics for this platform. This question seems out of scope. Feel free to ask about your data, trends, or predictions!",
    "I can't help with that particular question, but I'd be happy to analyze your business data. What metrics or insights are you looking for?",
]


# ── Classifier ────────────────────────────────────────────────────────────────

class QueryClassifier:
    """
    Classifies a natural language query using the LLM.
    Returns a ClassificationResult indicating relevance + engine type.
    """

    _ALLOWED_TYPES = {"sql", "analytical", "predictive", "rag", "rag++", "irrelevant"}

    async def classify(
        self,
        session: UserSession,
        query: str,
        audit: AuditLogger | None = None,
    ) -> ClassificationResult:
        """
        Classify the query. Uses the session's role-scoped schema and
        use-case context to make the classification contextually aware.
        """
        system_prompt, user_message = build_classifier_prompt(
            schema_str=session.schema_str,
            use_case_context=session.use_case_context,
            user_query=query,
            conversation_history=session.get_history_str(),
        )

        try:
            raw = await llm_json(
                system_prompt=system_prompt,
                user_message=user_message,
                temperature=0.0,   # Deterministic for classification
            )
        except Exception as exc:
            # Fallback keeps pipeline alive when provider output is empty/non-JSON.
            log.error(
                "Classifier llm_json failed: exc_type=%s exc_msg=%s query_preview=%r",
                type(exc).__name__,
                str(exc),
                query[:200],
            )
            if audit:
                audit.error("Classifier llm_json failed", exc=exc)
            return ClassificationResult(
                relevant=True,
                type="sql",
                sub_type="",
                reasoning="Fallback classification after LLM JSON failure",
                polite_rejection=None,
            )

        if not isinstance(raw, dict):
            log.warning("Classifier received non-dict JSON payload: type=%s", type(raw).__name__)
            raw = {}

        raw_relevant = raw.get("relevant", False)
        if isinstance(raw_relevant, str):
            relevant = raw_relevant.strip().lower() in {"true", "1", "yes"}
        else:
            relevant = bool(raw_relevant)

        raw_type = raw.get("type", "irrelevant")
        query_type = str(raw_type or "irrelevant").strip().lower()
        if query_type not in self._ALLOWED_TYPES:
            query_type = "irrelevant"

        raw_reasoning = raw.get("reasoning", "")
        reasoning = str(raw_reasoning or "").strip()

        raw_sub_type = raw.get("sub_type", "")
        sub_type = str(raw_sub_type or "").strip()

        log.debug(
            "Classifier normalized payload: relevant=%s type=%s sub_type=%s reasoning_chars=%s raw_keys=%s",
            relevant,
            query_type,
            sub_type,
            len(reasoning),
            sorted(raw.keys()),
        )

        # Force irrelevant type if not relevant
        if not relevant:
            query_type = "irrelevant"

        result = ClassificationResult(
            relevant=relevant,
            type=query_type,
            sub_type=sub_type,
            reasoning=reasoning,
            polite_rejection=REJECTION_RESPONSES[0] if not relevant else None,
        )

        if audit:
            audit.log(
                AuditEvent.QUERY_CLASSIFIED,
                details={
                    "query": query,
                    "type": query_type,
                    "relevant": relevant,
                    "reasoning": reasoning,
                },
            )

        return result
