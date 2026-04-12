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

from pydantic import BaseModel

from backend.core.logger import AuditEvent, AuditLogger
from backend.llm.client import llm_json
from backend.llm.context_manager import UserSession
from backend.llm.prompts.all_prompts import build_classifier_prompt


# ── Result Model ──────────────────────────────────────────────────────────────

class ClassificationResult(BaseModel):
    relevant: bool
    type: str      # sql | analytical | predictive | rag | rag++ | irrelevant
    sub_type: str = ""
    reasoning: str
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

        raw = await llm_json(
            system_prompt=system_prompt,
            user_message=user_message,
            temperature=0.0,   # Deterministic for classification
        )

        relevant: bool = raw.get("relevant", False)
        query_type: str = raw.get("type", "irrelevant").lower()
        reasoning: str = raw.get("reasoning", "")
        sub_type: str = raw.get("sub_type", "")

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
