"""
Model Evaluator — Automated performance metrics and model comparison utilities.
"""
from __future__ import annotations

from typing import Any

import numpy as np
from sklearn.metrics import (
    f1_score,
    mean_absolute_error,
    mean_squared_error,
    r2_score,
    roc_auc_score,
    silhouette_score,
)


def evaluate_regression(y_true: np.ndarray, y_pred: np.ndarray) -> dict[str, float]:
    """Standard regression metrics: RMSE, MAE, R²."""
    rmse = float(np.sqrt(mean_squared_error(y_true, y_pred)))
    mae = float(mean_absolute_error(y_true, y_pred))
    r2 = float(r2_score(y_true, y_pred))
    return {"rmse": round(rmse, 4), "mae": round(mae, 4), "r2": round(r2, 4)}


def evaluate_classification(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    y_proba: np.ndarray | None = None,
) -> dict[str, float]:
    """Classification metrics: F1, AUC-ROC (if probabilities available)."""
    is_binary = len(np.unique(y_true)) == 2
    avg = "binary" if is_binary else "weighted"
    f1 = float(f1_score(y_true, y_pred, average=avg, zero_division=0))
    metrics = {"f1": round(f1, 4)}

    if y_proba is not None and is_binary:
        try:
            auc = float(roc_auc_score(y_true, y_proba[:, 1]))
            metrics["auc"] = round(auc, 4)
        except Exception:
            pass

    return metrics


def evaluate_clustering(X: np.ndarray, labels: np.ndarray) -> dict[str, float]:
    """Clustering metric: Silhouette Score."""
    if len(set(labels)) < 2:
        return {"silhouette": 0.0}
    score = float(silhouette_score(X, labels))
    return {"silhouette": round(score, 4)}


def compare_versions(
    old_metrics: dict[str, float],
    new_metrics: dict[str, float],
    task_type: str,
) -> dict[str, Any]:
    """
    Compare two model versions and determine which is better.
    Returns: {
        "winner": "new" | "old",
        "improvements": {metric: change_pct},
        "should_promote": bool
    }
    """
    improvements = {}
    should_promote = False

    primary = "rmse" if task_type == "regression" else "f1"
    old_val = old_metrics.get(primary, 0)
    new_val = new_metrics.get(primary, 0)

    if old_val != 0:
        change_pct = ((new_val - old_val) / abs(old_val)) * 100
        improvements[primary] = round(change_pct, 2)

        if task_type == "regression":
            should_promote = new_val < old_val  # Lower RMSE = better
        else:
            should_promote = new_val > old_val  # Higher F1 = better

    return {
        "winner": "new" if should_promote else "old",
        "improvements": improvements,
        "should_promote": should_promote,
        "old_score": old_val,
        "new_score": new_val,
        "primary_metric": primary,
    }
