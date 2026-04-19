"""
Auth API — Login via Supabase GoTrue, issue a UQS backend JWT.

Role extraction order (most authoritative first):
  1. app_metadata.role  (set by server-side scripts / Supabase dashboard)
  2. user_metadata.role (set by the user at signup, or by admin)
  3. raw_user_meta_data.role (alternative key Supabase sometimes uses)
  4. Email-based heuristic (fallback, safe default)

`manager` is treated as a first-class role identical to `admin` in UQS.
"""
from __future__ import annotations

import logging

import httpx
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from backend.config import settings
from backend.core.auth import create_access_token

router = APIRouter(prefix="/api/auth", tags=["auth"])
log = logging.getLogger("uqs.auth")

# Roles that map directly to `admin` access inside UQS
ADMIN_ALIASES = {"admin", "manager", "superadmin", "owner", "super_admin"}

# Supabase role → UQS role mapping table
ROLE_MAP: dict[str, str] = {
    "admin":            "admin",
    "manager":          "manager",   # manager is its own first-class role now
    "superadmin":       "admin",
    "super_admin":      "admin",
    "owner":            "admin",
    "analyst":          "analyst",
    "data_analyst":     "analyst",
    "regional_manager": "regional_manager",
    "auditor":          "auditor",
    "audit":            "auditor",
    "viewer":           "viewer",
    "read_only":        "viewer",
    "employee":         "viewer",
    "authenticated":    "viewer",   # default Supabase role — least privilege
}


def _extract_role(user_data: dict) -> str:
    """
    Extract the UQS role from Supabase user data with a multi-source check.
    Tries the most-authoritative sources first, falls back gracefully.
    """
    email: str = user_data.get("email", "")

    # Priority 1: app_metadata (server-set, cannot be spoofed by user)
    app_meta: dict = user_data.get("app_metadata") or {}
    raw_role = (
        app_meta.get("role")
        or app_meta.get("uqs_role")
    )

    # Priority 2: user_metadata (user-set at signup or via admin)
    if not raw_role:
        user_meta: dict = user_data.get("user_metadata") or {}
        raw_role = (
            user_meta.get("role")
            or user_meta.get("uqs_role")
        )

    # Priority 3: raw_user_meta_data (alternative key Supabase sometimes uses)
    if not raw_role:
        raw_meta: dict = user_data.get("raw_user_meta_data") or {}
        raw_role = raw_meta.get("role") or raw_meta.get("uqs_role")

    # Priority 4: email heuristic (safe fallback)
    if not raw_role:
        email_lower = email.lower()
        if any(k in email_lower for k in ("admin", "superadmin")):
            raw_role = "admin"
        elif "manager" in email_lower:
            raw_role = "manager"
        elif any(k in email_lower for k in ("analyst", "sharma", "data")):
            raw_role = "analyst"
        elif "audit" in email_lower:
            raw_role = "auditor"
        else:
            raw_role = "viewer"

    # Normalise → UQS role
    raw_role_lower = (raw_role or "").strip().lower().replace("-", "_").replace(" ", "_")
    uqs_role = ROLE_MAP.get(raw_role_lower, raw_role_lower or "viewer")

    log.info(
        "Role extraction: email=%s raw_role=%s uqs_role=%s "
        "app_meta_role=%s user_meta_role=%s",
        email,
        raw_role,
        uqs_role,
        app_meta.get("role"),
        (user_data.get("user_metadata") or {}).get("role"),
    )
    return uqs_role


class LoginRequest(BaseModel):
    email: str
    password: str
    tenant_id: str | None = None  # for future multi-tenancy


@router.post("/login")
async def login(credentials: LoginRequest):
    """
    Authenticate against Supabase Auth (GoTrue).
    Extracts the user's role from app_metadata/user_metadata and issues
    a UQS backend JWT with that role embedded.
    """
    url = f"{settings.supabase_url}/auth/v1/token?grant_type=password"
    headers = {
        "apikey": settings.supabase_anon_key,
        "Content-Type": "application/json",
    }
    payload = {
        "email": credentials.email,
        "password": credentials.password,
    }

    async with httpx.AsyncClient() as client:
        try:
            resp = await client.post(url, headers=headers, json=payload, timeout=10.0)
        except Exception as exc:
            log.error("Supabase Auth connection error: %s", exc)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Could not reach authentication provider.",
            )

    if resp.status_code != 200:
        error_msg = "Invalid credentials"
        try:
            body = resp.json()
            error_msg = (
                body.get("error_description")
                or body.get("msg")
                or body.get("error")
                or error_msg
            )
        except Exception:
            pass
        log.warning("Login failed: email=%s status=%s msg=%s", credentials.email, resp.status_code, error_msg)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=error_msg)

    auth_data = resp.json()
    user_data: dict = auth_data.get("user") or {}
    user_id: str = user_data.get("id", "u_unknown")
    email: str = user_data.get("email", credentials.email)

    uqs_role = _extract_role(user_data)

    # Issue UQS backend JWT
    token = create_access_token(user_id=user_id, role=uqs_role, email=email)
    log.info("Login success: email=%s assigned_role=%s", email, uqs_role)

    return {
        "access_token": token,
        "token_type": "bearer",
        "role": uqs_role,
        "email": email,
        # Extra info for UI display
        "is_admin": uqs_role in ADMIN_ALIASES,
        "display_name": email.split("@")[0].replace(".", " ").replace("_", " ").title(),
    }


@router.get("/roles")
async def public_roles():
    """
    Public endpoint (no auth needed) — returns available roles from DB.
    Used by the login screen to show what roles exist.
    """
    from backend.core.rbac import get_all_roles
    roles = await get_all_roles()
    return {"roles": roles}
