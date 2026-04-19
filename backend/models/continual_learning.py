"""
Continual Learning — Daily model retraining pipeline.
Triggered by cron at 5AM. Retrains all active model targets on fresh data.
If the new model outperforms the current active version, it is promoted.
Otherwise, the previous version remains active (auto-rollback).
"""
from __future__ import annotations

import io
from datetime import datetime, timezone

import pandas as pd
from sqlalchemy import text

from backend.core.database import get_db_session
from backend.core.logger import AuditEvent, system_logger
from backend.models.registry import model_registry
from backend.models.trainer import ModelTrainer, TaskType


async def retrain_target(target_name: str) -> dict:
    """
    Retrain a single prediction target.
    - Fetches fresh data from DB
    - Trains new model version
    - Compares against current active version
    - Promotes if performance improved
    """
    trainer = ModelTrainer()

    # ── Load current active metadata for comparison ────────────────────────
    current_version = model_registry.get_active_version(target_name)
    current_metadata = model_registry.get_metadata(target_name, current_version) if current_version else {}
    current_metrics = current_metadata.get("metrics", {})

    data_sql = current_metadata.get("data_sql", "")
    target_col = current_metadata.get("target_column", "")
    task_type: TaskType = current_metadata.get("task_type", "regression")
    features: list[str] = current_metadata.get("features", [])

    if not data_sql or not target_col:
        return {"target": target_name, "status": "skipped", "reason": "No data_sql or target_column in metadata"}

    # ── Fetch fresh data ───────────────────────────────────────────────────
    async with get_db_session() as db:
        result = await db.execute(text(data_sql))
        columns = list(result.keys())
        rows = result.fetchall()

    df = pd.DataFrame(rows, columns=columns)

    if df.empty:
        return {"target": target_name, "status": "skipped", "reason": "Empty dataset"}

    # ── Train new model ────────────────────────────────────────────────────
    new_model, training_result = await trainer.train(
        df=df,
        target_col=target_col,
        task_type=task_type,
        target_name=target_name,
    )

    # ── Save new version ───────────────────────────────────────────────────
    metadata = {
        "model_type": training_result.best_model_type,
        "metrics": training_result.metrics,
        "features": training_result.features,
        "all_scores": training_result.all_model_scores,
        "task_type": task_type,
        "target_column": target_col,
        "data_sql": data_sql,
        "trained_at": datetime.now(timezone.utc).isoformat(),
    }
    new_version = model_registry.save_model(
        target=target_name,
        model=new_model,
        metadata=metadata,
        dataset_hash=training_result.dataset_hash,
    )

    # ── Compare metrics and decide whether to promote ─────────────────────
    promoted = False
    promotion_reason = ""

    new_metrics = training_result.metrics
    primary_metric = "rmse" if task_type == "regression" else "f1"

    new_score = new_metrics.get(primary_metric, 0)
    old_score = current_metrics.get(primary_metric, None)

    if old_score is None:
        # First version — always promote
        model_registry.promote(target_name, new_version)
        promoted = True
        promotion_reason = "First version — auto-promoted"
    elif task_type == "regression":
        # Lower RMSE = better
        if new_score < old_score:
            model_registry.promote(target_name, new_version)
            promoted = True
            promotion_reason = f"RMSE improved: {old_score:.4f} → {new_score:.4f}"
        else:
            promotion_reason = f"RMSE did not improve ({new_score:.4f} >= {old_score:.4f}), keeping v{current_version}"
    else:
        # Higher F1 = better
        if new_score > old_score:
            model_registry.promote(target_name, new_version)
            promoted = True
            promotion_reason = f"F1 improved: {old_score:.4f} → {new_score:.4f}"
        else:
            promotion_reason = f"F1 did not improve ({new_score:.4f} <= {old_score:.4f}), keeping v{current_version}"

    system_logger.log(
        AuditEvent.MODEL_PROMOTED if promoted else AuditEvent.MODEL_TRAINED,
        details={
            "target": target_name,
            "new_version": new_version,
            "promoted": promoted,
            "reason": promotion_reason,
            "metrics": new_metrics,
        },
    )

    return {
        "target": target_name,
        "new_version": new_version,
        "promoted": promoted,
        "metrics": new_metrics,
        "promotion_reason": promotion_reason,
    }


async def run_all_retraining() -> list[dict]:
    """Retrain all registered model targets. Called by cron at 5AM."""
    targets = model_registry.list_targets()
    results = []
    for target in targets:
        try:
            result = await retrain_target(target)
            results.append(result)
        except Exception as e:
            results.append({"target": target, "status": "error", "reason": str(e)})
    return results


async def bootstrap_models_on_startup() -> dict:
    """
    Run a one-time retraining pass on app startup.

    This reuses the same dataset-backed retraining flow as the admin/cron path,
    but executes automatically once when the service starts.
    """
    targets = model_registry.list_targets()
    if not targets:
        return {
            "status": "skipped",
            "reason": "No registered predictive targets found",
            "targets": [],
            "results": [],
        }

    results: list[dict] = []
    for target in targets:
        try:
            result = await retrain_target(target)
            results.append(result)
        except Exception as exc:
            results.append({"target": target, "status": "error", "reason": str(exc)})

    return {
        "status": "completed",
        "targets": targets,
        "results": results,
        "total_targets": len(targets),
    }
