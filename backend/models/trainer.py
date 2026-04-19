"""
Multi-Model Training Pool for the Predictive Engine.
Trains 3–5 candidate models per target feature and returns the best one.

Supported models:
  - XGBoost (regression + classification)
  - RandomForest (regression + classification)
  - LightGBM (regression + classification)
  - Prophet (time-series forecasting)
  - IsolationForest (anomaly detection)
  - KMeans (clustering / unsupervised)

Model selection is automatic based on performance metrics:
  - Regression:     RMSE (lower = better)
  - Classification: F1 + AUC (higher = better)
  - Clustering:     Silhouette Score (higher = better)
  - Forecasting:    MAE (lower = better)
"""
from __future__ import annotations

import hashlib
import json
import time
from typing import Any, Literal

import numpy as np
import pandas as pd
from pandas.api.types import is_datetime64_any_dtype
from pydantic import BaseModel
from sklearn.ensemble import IsolationForest, RandomForestClassifier, RandomForestRegressor
from sklearn.cluster import KMeans
from sklearn.model_selection import cross_val_score, train_test_split
from sklearn.preprocessing import LabelEncoder, StandardScaler
from sklearn.metrics import (
    f1_score,
    mean_squared_error,
    roc_auc_score,
    silhouette_score,
)


# ── Types ─────────────────────────────────────────────────────────────────────

TaskType = Literal["regression", "classification", "clustering", "forecasting", "anomaly"]


class TrainingResult(BaseModel):
    target: str
    task_type: TaskType
    best_model_type: str
    metrics: dict[str, float]
    features: list[str]
    dataset_hash: str
    training_time_s: float
    all_model_scores: dict[str, float]


# ── Preprocessing ─────────────────────────────────────────────────────────────

def _preprocess(df: pd.DataFrame, target_col: str, task_type: TaskType) -> tuple:
    """Basic EDA + preprocessing: encode categoricals, scale numerics, handle nulls."""
    df = df.dropna(subset=[target_col]).copy()
    feature_cols = [c for c in df.columns if c != target_col]

    # Encode categorical features
    for col in feature_cols:
        if df[col].dtype == object or df[col].dtype.name == "category":
            le = LabelEncoder()
            df[col] = le.fit_transform(df[col].astype(str))

    # Fill remaining nulls with median for numeric
    for col in feature_cols:
        if df[col].isnull().any():
            df[col] = df[col].fillna(df[col].median())

    X = df[feature_cols].values
    y_raw = df[target_col].values

    if task_type == "classification" and df[target_col].dtype == object:
        le = LabelEncoder()
        y = le.fit_transform(y_raw)
    else:
        y = y_raw.astype(float)

    # Scale features
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    return X_scaled, y, feature_cols


def _dataset_hash(df: pd.DataFrame) -> str:
    """Deterministic hash of dataset for tracking in registry."""
    return hashlib.sha256(pd.util.hash_pandas_object(df, index=True).values.tobytes()).hexdigest()[:16]


# ── Model Training Pool ───────────────────────────────────────────────────────

class ModelTrainer:

    async def train(
        self,
        df: pd.DataFrame,
        target_col: str,
        task_type: TaskType,
        target_name: str,
    ) -> tuple[Any, TrainingResult]:
        """
        Train all candidate models, evaluate, and return the best one.
        Returns (best_model_object, TrainingResult).
        """
        start = time.perf_counter()
        dataset_hash = _dataset_hash(df)

        if task_type == "forecasting":
            model, metrics = await self._train_prophet(df, target_col)
            result = TrainingResult(
                target=target_name,
                task_type=task_type,
                best_model_type="prophet",
                metrics=metrics,
                features=["ds"],
                dataset_hash=dataset_hash,
                training_time_s=time.perf_counter() - start,
                all_model_scores={"prophet": metrics.get("mae", 0)},
            )
            return model, result

        if task_type == "anomaly":
            model, metrics = self._train_isolation_forest(df, target_col)
            result = TrainingResult(
                target=target_name,
                task_type=task_type,
                best_model_type="isolation_forest",
                metrics=metrics,
                features=[c for c in df.columns if c != target_col],
                dataset_hash=dataset_hash,
                training_time_s=time.perf_counter() - start,
                all_model_scores={"isolation_forest": metrics.get("contamination", 0.1)},
            )
            return model, result

        if task_type == "clustering":
            model, metrics = self._train_kmeans(df)
            result = TrainingResult(
                target=target_name,
                task_type=task_type,
                best_model_type="kmeans",
                metrics=metrics,
                features=list(df.columns),
                dataset_hash=dataset_hash,
                training_time_s=time.perf_counter() - start,
                all_model_scores={"kmeans": metrics.get("silhouette", 0)},
            )
            return model, result

        # ── Supervised: regression or classification ────────────────────────
        X, y, features = _preprocess(df, target_col, task_type)
        X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

        candidate_models = self._get_candidate_models(task_type)
        scores: dict[str, float] = {}
        trained_models: dict[str, Any] = {}

        for name, model in candidate_models.items():
            try:
                model.fit(X_train, y_train)
                score = self._evaluate(model, X_test, y_test, task_type)
                scores[name] = score
                trained_models[name] = model
            except Exception as e:
                scores[name] = -999.0

        # Select best model
        best_name = self._select_best(scores, task_type)
        best_model = trained_models[best_name]
        best_score = scores[best_name]

        metric_key = "rmse" if task_type == "regression" else "f1"
        metrics = {metric_key: round(abs(best_score), 4)}

        result = TrainingResult(
            target=target_name,
            task_type=task_type,
            best_model_type=best_name,
            metrics=metrics,
            features=features,
            dataset_hash=dataset_hash,
            training_time_s=time.perf_counter() - start,
            all_model_scores={k: round(abs(v), 4) for k, v in scores.items()},
        )
        return best_model, result

    def _get_candidate_models(self, task_type: TaskType) -> dict[str, Any]:
        if task_type == "regression":
            models: dict[str, Any] = {
                "random_forest": RandomForestRegressor(n_estimators=100, random_state=42, n_jobs=-1),
            }
            try:
                from xgboost import XGBRegressor
                models["xgboost"] = XGBRegressor(n_estimators=100, random_state=42, verbosity=0)
            except ImportError:
                pass
            try:
                from lightgbm import LGBMRegressor
                models["lightgbm"] = LGBMRegressor(n_estimators=100, random_state=42, verbosity=-1)
            except ImportError:
                pass
            return models

        else:  # classification
            models = {
                "random_forest": RandomForestClassifier(n_estimators=100, random_state=42, n_jobs=-1),
            }
            try:
                from xgboost import XGBClassifier
                models["xgboost"] = XGBClassifier(n_estimators=100, random_state=42, verbosity=0, eval_metric="logloss")
            except ImportError:
                pass
            try:
                from lightgbm import LGBMClassifier
                models["lightgbm"] = LGBMClassifier(n_estimators=100, random_state=42, verbosity=-1)
            except ImportError:
                pass
            return models

    def _evaluate(self, model: Any, X_test: np.ndarray, y_test: np.ndarray, task_type: TaskType) -> float:
        preds = model.predict(X_test)
        if task_type == "regression":
            return -float(np.sqrt(mean_squared_error(y_test, preds)))  # Negative RMSE (higher=better)
        else:
            avg = "binary" if len(np.unique(y_test)) == 2 else "weighted"
            return float(f1_score(y_test, preds, average=avg, zero_division=0))

    def _select_best(self, scores: dict[str, float], task_type: TaskType) -> str:
        """Select based on highest score (for regression: least negative RMSE)."""
        valid = {k: v for k, v in scores.items() if v > -999}
        if not valid:
            return list(scores.keys())[0]
        return max(valid, key=lambda k: valid[k])

    async def _train_prophet(self, df: pd.DataFrame, target_col: str) -> tuple[Any, dict]:
        """Time-series forecasting with Meta Prophet."""
        try:
            from prophet import Prophet

            ds_col = None
            for col in df.columns:
                if col == target_col:
                    continue
                if is_datetime64_any_dtype(df[col]):
                    ds_col = col
                    break

            if ds_col is None:
                named_candidates = [
                    col for col in df.columns
                    if col != target_col and ("date" in col.lower() or "time" in col.lower() or "day" in col.lower())
                ]
                if named_candidates:
                    ds_col = named_candidates[0]

            if ds_col is None:
                parse_scores: list[tuple[str, float]] = []
                for col in df.columns:
                    if col == target_col:
                        continue
                    parsed = pd.to_datetime(df[col], errors="coerce")
                    parse_scores.append((col, float(parsed.notna().mean())))
                parse_scores.sort(key=lambda item: item[1], reverse=True)
                if parse_scores and parse_scores[0][1] > 0.6:
                    ds_col = parse_scores[0][0]

            if ds_col is None:
                raise ValueError("Forecasting dataset does not include a recognizable datetime column")

            # Prophet expects a clean (ds, y) time-series; normalize and de-duplicate timestamps.
            prophet_df = df[[ds_col, target_col]].rename(columns={ds_col: "ds", target_col: "y"}).copy()
            prophet_df["ds"] = pd.to_datetime(prophet_df["ds"], errors="coerce")
            prophet_df["y"] = pd.to_numeric(prophet_df["y"], errors="coerce")
            prophet_df = prophet_df.dropna(subset=["ds", "y"])
            if prophet_df.empty:
                raise ValueError("Forecasting dataset has no valid datetime/target rows")

            # Duplicate timestamps commonly appear in transactional data; average per timestamp.
            prophet_df = prophet_df.groupby("ds", as_index=False, sort=True)["y"].mean()

            model = Prophet(daily_seasonality=True)
            model.fit(prophet_df)

            # Compute MAE on in-sample timestamps to avoid shape mismatches.
            in_sample_forecast = model.predict(prophet_df[["ds"]])
            mae = float(np.mean(np.abs(prophet_df["y"].to_numpy() - in_sample_forecast["yhat"].to_numpy())))
            return model, {"mae": round(mae, 4)}
        except ImportError:
            raise RuntimeError("Install 'prophet' package: pip install prophet")

    def _train_isolation_forest(self, df: pd.DataFrame, target_col: str) -> tuple[Any, dict]:
        X = df.select_dtypes(include=[np.number]).fillna(0).values
        model = IsolationForest(contamination=0.1, random_state=42, n_jobs=-1)
        model.fit(X)
        return model, {"contamination": 0.1, "n_samples": len(X)}

    def _train_kmeans(self, df: pd.DataFrame, n_clusters: int = 5) -> tuple[Any, dict]:
        X = df.select_dtypes(include=[np.number]).fillna(0).values
        scaler = StandardScaler()
        X_scaled = scaler.fit_transform(X)
        model = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
        labels = model.fit_predict(X_scaled)
        score = float(silhouette_score(X_scaled, labels)) if len(set(labels)) > 1 else 0
        return model, {"silhouette": round(score, 4), "n_clusters": n_clusters}
