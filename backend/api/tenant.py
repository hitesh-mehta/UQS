"""
Tenant API — Multi-tenant registration and management endpoints.

POST /api/tenant/register   — Admin registers their Supabase project
GET  /api/tenant/{id}/info  — Public: get tenant name/supabase_url for login screen
GET  /api/tenant/list       — Admin only: list all tenants
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from backend.core.auth import UserContext, require_admin, get_current_user

router = APIRouter(prefix="/api/tenant", tags=["tenant"])
log = logging.getLogger("uqs.tenant")


class TenantRegisterRequest(BaseModel):
    name: str                    # Company / department name
    supabase_url: str            # https://your-project.supabase.co
    anon_key: str
    service_key: str
    db_url: str                  # postgresql://... connection string
    contact_email: str


@router.post("/register")
async def register_tenant(
    body: TenantRegisterRequest,
) -> dict:
    """
    Register a new tenant (company/department).
    No auth required — anyone can register their own Supabase project.
    Returns a tenant_id and an access_url to share with employees.
    """
    from backend.core.tenant_manager import register_tenant as _register

    try:
        result = await _register(
            name=body.name,
            supabase_url=body.supabase_url,
            anon_key=body.anon_key,
            service_key=body.service_key,
            db_url=body.db_url,
            contact_email=body.contact_email,
        )
        tenant_id = result["tenant_id"]
        return {
            "tenant_id": tenant_id,
            "name": result["name"],
            "access_url": f"/?tenant={tenant_id}",
            "message": (
                f"Tenant '{body.name}' registered successfully. "
                f"Share the access_url with your employees."
            ),
        }
    except Exception as exc:
        log.error("Tenant registration failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Registration failed: {str(exc)[:200]}",
        )


@router.get("/list")
async def list_tenants(
    admin: UserContext = Depends(require_admin),
) -> dict:
    """List all registered tenants. Admin only."""
    from backend.core.tenant_manager import list_tenants as _list
    tenants = await _list()
    return {"tenants": tenants, "total": len(tenants)}


@router.get("/{tenant_id}/info")
async def get_tenant_info(tenant_id: str) -> dict:
    """
    Public endpoint — returns safe tenant info for the login screen.
    Used when a user follows a ?tenant=<uuid> link.
    """
    from backend.core.tenant_manager import get_tenant_info as _info
    info = await _info(tenant_id)
    if not info:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant not found or inactive.",
        )
    return info
