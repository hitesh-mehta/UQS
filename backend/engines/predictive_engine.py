"""
Predictive Engine — ML inference endpoint.
Loads the active model for a prediction target and runs inference.
Also handles the prediction request itself: pulling live DB data,
preprocessing it, and returning predictions with confidence intervals.
"""
from __future__ import annotations

import time
from typing import Any

import numpy as np
import pandas as pd
from pydantic import BaseModel

from backend.core.database import get_db_session
from backend.core.logger import AuditEvent, AuditLogger
from backend.engines.sql_engine import SQLEngine
from backend.llm.client import llm_json
from backend.llm.context_manager import UserSession
from backend.models.registry import model_registry
from backend.models.trainer import ModelTrainer, TaskType


# ── Result Models ─────────────────────────────────────────────────────────────

class PredictionItem(BaseModel):
    entity: str
    prediction: float | str
    confidence: float | None = None
    label: str | None = None   # e.g. "High churn risk"


class PredictiveResult(BaseModel):
    target: str
    task_type: str
    predictions: list[PredictionItem]
    narrative: str
    model_version: int | None
    model_type: str
    sources: list[str]
    latency_ms: float
    confidence_interval: dict[str, float] | None = None  # For regression/forecasting


# ── Predictive Engine ─────────────────────────────────────────────────────────

class PredictiveEngine:
    def __init__(self):
        self._sql_engine = SQLEngine()
        self._trainer = ModelTrainer()

    async def run(
        self,
        session: UserSession,
        query: str,
        audit: AuditLogger | None = None,
    ) -> PredictiveResult:
        start = time.perf_counter()

        # ── Step 1: LLM determines target + required data ──────────────────
        plan = await self._plan_prediction(session, query)
        target_name = plan.get("target_name", "unknown")
        task_type: TaskType = plan.get("task_type", "regression")
        data_sql = plan.get("data_sql", "")
        entity_column = plan.get("entity_column", "id")

        # ── Step 2: Load active model ──────────────────────────────────────
        try:
            model, metadata = model_registry.load_model(target_name)
            model_version = metadata.get("version")
            model_type = metadata.get("model_type", "unknown")
            feature_cols: list[str] = metadata.get("features", [])
        except ValueError:
            # No model trained yet — trigger training
            model_version = None
            model_type = "untrained"
            latency_ms = (time.perf_counter() - start) * 1000
            return PredictiveResult(
                target=target_name,
                task_type=task_type,
                predictions=[],
                narrative=(
                    f"No trained model found for '{target_name}'. "
                    f"Please ask an admin to trigger training for this target."
                ),
                model_version=None,
                model_type="untrained",
                sources=[],
                latency_ms=latency_ms,
            )

        # ── Step 3: Fetch live data for inference ──────────────────────────
        from sqlalchemy import text
        async with get_db_session() as db:
            result = await db.execute(text(data_sql))
            columns = list(result.keys())
            rows = result.fetchall()

        df = pd.DataFrame(rows, columns=columns)
        entities = df[entity_column].tolist() if entity_column in df.columns else list(range(len(df)))

        # Use only the features the model was trained on
        available_features = [f for f in feature_cols if f in df.columns]
        X = df[available_features].fillna(0).values if available_features else df.select_dtypes(include=[np.number]).fillna(0).values

        # ── Step 4: Run inference ──────────────────────────────────────────
        raw_preds = model.predict(X)
        confidence = None

        # For classifiers that support probability
        if hasattr(model, "predict_proba"):
            try:
                proba = model.predict_proba(X)
                confidence_scores = proba.max(axis=1).tolist()
            except Exception:
                confidence_scores = [None] * len(raw_preds)
        else:
            confidence_scores = [None] * len(raw_preds)

        # ── Step 5: Build prediction items ────────────────────────────────
        predictions = []
        for entity, pred, conf in zip(entities, raw_preds, confidence_scores):
            if task_type == "classification":
                label = self._classify_label(pred, target_name)
            else:
                label = None
            predictions.append(PredictionItem(
                entity=str(entity),
                prediction=float(pred) if isinstance(pred, (int, float, np.number)) else str(pred),
                confidence=round(float(conf), 3) if conf is not None else None,
                label=label,
            ))

        # ── Step 6: LLM narrative ──────────────────────────────────────────
        pred_summary = f"Top predictions for {target_name}:\n"
        for p in predictions[:5]:
            pred_summary += f"  {p.entity}: {p.prediction}"
            if p.label:
                pred_summary += f" ({p.label})"
            if p.confidence:
                pred_summary += f" [confidence: {p.confidence:.1%}]"
            pred_summary += "\n"

        narrative_raw = await llm_json(
            system_prompt=f"You are a predictive analytics narrator. Summarize these {task_type} predictions for business stakeholders.",
            user_message=f"Query: '{query}'\n\n{pred_summary}\n\nProvide a clear narrative (JSON: {{\"narrative\": \"...\"}})",
            temperature=0.2,
        )
        narrative = narrative_raw.get("narrative", pred_summary)

        latency_ms = (time.perf_counter() - start) * 1000

        if audit:
            audit.log(AuditEvent.ENGINE_RESPONSE, details={
                "engine": "predictive",
                "target": target_name,
                "n_predictions": len(predictions),
                "model_version": model_version,
            }, latency_ms=latency_ms)

        return PredictiveResult(
            target=target_name,
            task_type=task_type,
            predictions=predictions[:20],
            narrative=narrative,
            model_version=model_version,
            model_type=model_type,
            sources=[data_sql.split("FROM")[-1].split()[0] if "FROM" in data_sql.upper() else "DB"],
            latency_ms=latency_ms,
        )

    async def _plan_prediction(self, session: UserSession, query: str) -> dict:
        """Ask LLM to determine what to predict and how to fetch the data."""
        system = f"""You are a prediction planner for a {session.use_case_context}.

Available schema:
{session.schema_str}

Available trained model targets: {model_registry.list_targets()}

Given a prediction question, determine:
1. The prediction target name (must match an existing target if possible)
2. The task type: regression | classification | clustering | forecasting | anomaly
3. A SQL query to fetch the current data needed for prediction
4. The entity column that identifies each row (e.g. customer_id)

Respond in JSON:
{{
  "target_name": "...",
  "task_type": "regression|classification|clustering|forecasting|anomaly",
  "data_sql": "SELECT ... FROM ...",
  "entity_column": "customer_id"
}}"""
        result = await llm_json(system, f"Prediction query: '{query}'", temperature=0.0)
        return result

    def _classify_label(self, pred: Any, target: str) -> str:
        """Convert numeric prediction to human-friendly label."""
        labels = {
            "churn": {0: "Low churn risk", 1: "High churn risk"},
            "fraud": {0: "Legitimate", 1: "Suspicious"},
        }
        for key, mapping in labels.items():
            if key in target.lower():
                try:
                    return mapping.get(int(pred), str(pred))
                except (ValueError, TypeError):
                    pass
        return str(pred)
