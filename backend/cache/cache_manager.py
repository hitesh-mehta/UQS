"""
Cache Intelligence Layer — 4-granularity FIFO report cache.

Granularities: hourly (10 units) | daily (10 units) | weekly (10 units) | monthly (10 units)
Eviction policy: FIFO — when 11th unit is added, the 1st is removed.

Each cached report contains:
  - Summary narrative (LLM-generated)
  - Key metrics snapshot
  - Trend analysis
  - Anomaly flags
  - Top contributors per KPI
  - Raw aggregated data tables
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, Optional

from pydantic import BaseModel

from backend.config import settings


# ── Types ─────────────────────────────────────────────────────────────────────

Granularity = Literal["hourly", "daily", "weekly", "monthly"]

RETENTION_MAP: dict[Granularity, int] = {
    "hourly": settings.cache_retention_units,
    "daily": settings.cache_retention_units,
    "weekly": settings.cache_retention_units,
    "monthly": settings.cache_retention_units,
}


# ── Report Model ──────────────────────────────────────────────────────────────

class CachedReport(BaseModel):
    granularity: Granularity
    period: str                    # e.g. "2024-02-01" for daily, "2024-W07" for weekly
    generated_at: str
    coverage: str                  # Human-readable period description
    metrics: list[str]             # List of metric names covered
    summary_narrative: str         # LLM-generated text summary
    key_metrics: list[dict]        # [{label, value, change}]
    trend_analysis: dict           # {metric: {direction, slope}}
    anomaly_flags: list[dict]      # [{metric, value, severity, description}]
    top_contributors: dict         # {metric: [{label, value, share_pct}]}
    raw_data: dict                 # Raw aggregated tables


# ── Cache Store ───────────────────────────────────────────────────────────────

class CacheManager:
    """
    Manages the 4-granularity FIFO report cache.
    Reports are stored as JSON files in the configured cache store path.
    """

    def __init__(self):
        self.base_path = Path(settings.cache_store_path)
        self.base_path.mkdir(parents=True, exist_ok=True)
        # Create subdirectories for each granularity
        for gran in ["hourly", "daily", "weekly", "monthly"]:
            (self.base_path / gran).mkdir(exist_ok=True)

    def _report_file(self, granularity: Granularity, period: str) -> Path:
        safe_period = period.replace(":", "-").replace("/", "-")
        return self.base_path / granularity / f"{safe_period}.json"

    def _index_file(self, granularity: Granularity) -> Path:
        return self.base_path / granularity / "_index.json"

    def _load_index(self, granularity: Granularity) -> list[str]:
        """Returns ordered list of periods (oldest first)."""
        idx_file = self._index_file(granularity)
        if not idx_file.exists():
            return []
        with open(idx_file) as f:
            return json.load(f)

    def _save_index(self, granularity: Granularity, index: list[str]) -> None:
        with open(self._index_file(granularity), "w") as f:
            json.dump(index, f)

    # ── CRUD operations ───────────────────────────────────────────────────

    def store_report(self, report: CachedReport) -> dict:
        """
        Store a report with FIFO eviction.
        If the cache already has MAX_UNITS entries, the oldest is evicted.
        """
        granularity = report.granularity
        max_units = RETENTION_MAP[granularity]
        index = self._load_index(granularity)

        # FIFO eviction
        evicted = None
        while len(index) >= max_units:
            oldest_period = index.pop(0)
            oldest_file = self._report_file(granularity, oldest_period)
            if oldest_file.exists():
                oldest_file.unlink()
            evicted = oldest_period

        # Write new report
        report_file = self._report_file(granularity, report.period)
        with open(report_file, "w") as f:
            f.write(report.model_dump_json(indent=2))

        index.append(report.period)
        self._save_index(granularity, index)

        return {"stored": report.period, "evicted": evicted, "total": len(index)}

    def get_report(self, granularity: Granularity, period: str) -> Optional[CachedReport]:
        """Retrieve a specific cached report."""
        report_file = self._report_file(granularity, period)
        if not report_file.exists():
            return None
        with open(report_file) as f:
            return CachedReport.model_validate_json(f.read())

    def list_reports(self, granularity: Optional[Granularity] = None) -> dict[str, list[str]]:
        """List all available cached reports by granularity."""
        if granularity:
            return {granularity: self._load_index(granularity)}
        return {
            gran: self._load_index(gran)
            for gran in ["hourly", "daily", "weekly", "monthly"]
        }

    def get_all_summaries(self) -> list[dict]:
        """
        Return lightweight summaries of all cached reports.
        Used by the LLM cache-hit detection prompt.
        """
        summaries = []
        for gran in ["hourly", "daily", "weekly", "monthly"]:
            for period in self._load_index(gran):
                report = self.get_report(gran, period)  # type: ignore
                if report:
                    summaries.append({
                        "granularity": gran,
                        "period": period,
                        "coverage": report.coverage,
                        "metrics": report.metrics,
                        "summary": report.summary_narrative[:300],
                    })
        return summaries

    def get_report_section(self, granularity: Granularity, period: str, section: str) -> Optional[dict]:
        """Get a specific section of a cached report (e.g. key_metrics, trend_analysis)."""
        report = self.get_report(granularity, period)
        if not report:
            return None
        return getattr(report, section, None)

    def flush(self, granularity: Optional[Granularity] = None) -> dict:
        """Clear the cache. Admin-only in API layer."""
        import shutil
        cleared = {}
        grans = [granularity] if granularity else ["hourly", "daily", "weekly", "monthly"]
        for gran in grans:
            gran_dir = self.base_path / gran
            count = len(self._load_index(gran))
            for f in gran_dir.iterdir():
                if f.suffix == ".json":
                    f.unlink()
            cleared[gran] = count
        return cleared


# ── Global singleton ──────────────────────────────────────────────────────────
cache_manager = CacheManager()
