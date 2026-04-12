"""
Admin API — Cache flush, model rollback, and system management.
All routes require admin role JWT.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from backend.cache.cache_manager import Granularity, cache_manager
from backend.cache.cron_generator import generate_report
from backend.core.auth import UserContext, require_admin
from backend.core.logger import AuditEvent, AuditLogger
from backend.models.continual_learning import run_all_retraining
from backend.models.registry import model_registry

router = APIRouter(prefix="/api/admin", tags=["admin"])


# ── Cache Admin ───────────────────────────────────────────────────────────────

@router.post("/cache/flush")
async def flush_cache(
    granularity: Granularity | None = None,
    admin: UserContext = Depends(require_admin),
) -> dict:
    """Flush all cache or a specific granularity level."""
    result = cache_manager.flush(granularity)
    return {"flushed": result, "message": "Cache flushed successfully."}


@router.post("/cache/generate/{granularity}")
async def trigger_cache_generation(
    granularity: Granularity,
    admin: UserContext = Depends(require_admin),
) -> dict:
    """Manually trigger report generation for a given granularity."""
    report = await generate_report(granularity)
    return {"period": report.period, "granularity": granularity, "generated_at": report.generated_at}


# ── Model Admin ───────────────────────────────────────────────────────────────

@router.post("/models/rollback")
async def rollback_model(
    target: str,
    to_version: int,
    admin: UserContext = Depends(require_admin),
) -> dict:
    """
    Roll back a model target to a specific version.
    This deletes all model versions and datasets AFTER to_version.
    """
    audit = AuditLogger(user_id=admin.user_id, role=admin.role)
    result = model_registry.rollback(target=target, to_version=to_version, admin_only=True)
    audit.log(AuditEvent.MODEL_ROLLBACK, details=result)
    return result


@router.post("/models/retrain")
async def trigger_retraining(
    admin: UserContext = Depends(require_admin),
) -> dict:
    """Manually trigger the full retraining pipeline for all targets."""
    results = await run_all_retraining()
    return {"results": results, "targets_retrained": len(results)}


# ── Model API ─────────────────────────────────────────────────────────────────

@router.get("/models/registry")
async def get_model_registry(
    admin: UserContext = Depends(require_admin),
) -> dict:
    """Get full model registry summary."""
    return model_registry.get_registry_summary()


# ── Cache Status (readable by all authenticated users) ────────────────────────
from backend.core.auth import get_current_user

@router.get("/cache/status")
async def get_cache_status(
    user: UserContext = Depends(get_current_user),
) -> dict:
    """Get cache contents and available reports."""
    return {
        "reports": cache_manager.list_reports(),
        "summaries": cache_manager.get_all_summaries(),
    }
