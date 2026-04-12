"""
Basic tests for the Query Classification Engine.
"""
import pytest
import asyncio

# Minimal test — expand with real fixtures when DB is available

def test_classifier_module_imports():
    from backend.engines.classifier import QueryClassifier, ClassificationResult
    assert QueryClassifier is not None
    assert ClassificationResult is not None


def test_cache_manager_init():
    import tempfile, os
    from unittest.mock import patch
    with tempfile.TemporaryDirectory() as tmp:
        with patch("backend.config.settings.cache_store_path", tmp):
            from backend.cache.cache_manager import CacheManager
            cm = CacheManager()
            assert cm.list_reports() == {
                "hourly": [], "daily": [], "weekly": [], "monthly": []
            }


def test_model_registry_init():
    import tempfile
    from unittest.mock import patch
    with tempfile.TemporaryDirectory() as tmp:
        with patch("backend.config.settings.model_registry_path", tmp):
            from backend.models.registry import ModelRegistry
            registry = ModelRegistry()
            assert registry.list_targets() == []


def test_sql_safety():
    import asyncio
    from backend.engines.sql_engine import _is_safe_sql

    assert _is_safe_sql("SELECT * FROM sales_fact_view") == (True, "")
    safe, reason = _is_safe_sql("DELETE FROM sales_fact")
    assert not safe
    assert "DELETE" in reason

    safe, reason = _is_safe_sql("DROP TABLE users")
    assert not safe

    safe, reason = _is_safe_sql("UPDATE sales SET revenue = 0")
    assert not safe


def test_chunk_text():
    from backend.vector_store.ingestion import chunk_text
    text = " ".join([f"word{i}" for i in range(1000)])
    chunks = chunk_text(text, chunk_size=100, overlap=20)
    assert len(chunks) > 0
    assert all(isinstance(c, str) for c in chunks)
    assert all(len(c) > 0 for c in chunks)


def test_metric_dictionary():
    from backend.schema.metric_dict import MetricDictionary, DEFAULT_METRICS
    md = MetricDictionary()
    metric = md.find_by_alias("revenue")
    assert metric is not None
    assert metric.canonical_name == "Total Revenue"

    metric2 = md.find_by_alias("sales")
    assert metric2 is not None
    assert metric2.canonical_name == "Total Revenue"

    assert md.find_by_alias("nonexistent_xyz") is None
