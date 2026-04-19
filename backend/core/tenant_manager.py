"""
Multi-Tenant Manager for UQS.

Stores tenant registrations in the platform Supabase DB (uqs_tenants table).
Each tenant has their own Supabase project credentials.
Per-tenant DB sessions are created on-demand and pooled in memory.
"""
from __future__ import annotations

import logging
import uuid
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from backend.core.database import get_db_session

log = logging.getLogger("uqs.tenant_manager")

# In-memory cache: tenant_id → AsyncEngine
_tenant_engines: dict[str, AsyncEngine] = {}


def _build_engine(db_url: str) -> AsyncEngine:
    """Build an async SQLAlchemy engine for a given DB URL."""
    # Ensure asyncpg prefix
    if db_url.startswith("postgresql://"):
        db_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return create_async_engine(
        db_url,
        pool_size=3,
        max_overflow=5,
        pool_pre_ping=True,
        pool_recycle=300,
    )


async def get_tenant_engine(tenant_id: str) -> Optional[AsyncEngine]:
    """Get or create an engine for a tenant."""
    if tenant_id in _tenant_engines:
        return _tenant_engines[tenant_id]

    # Look up credentials from platform DB
    async with get_db_session() as session:
        result = await session.execute(
            text("SELECT db_url FROM uqs_tenants WHERE id = :tid AND active = true"),
            {"tid": tenant_id},
        )
        row = result.fetchone()

    if not row:
        return None

    db_url = row[0]
    engine = _build_engine(db_url)
    _tenant_engines[tenant_id] = engine
    log.info("Created DB engine for tenant: %s", tenant_id)
    return engine


async def register_tenant(
    name: str,
    supabase_url: str,
    anon_key: str,
    service_key: str,
    db_url: str,
    contact_email: str,
    admin_role: str = "admin",
) -> dict:
    """
    Register a new tenant. Stores credentials in uqs_tenants table.
    Returns tenant_id and the access URL to share with employees.
    """
    tenant_id = str(uuid.uuid4())

    async def _has_admin_role_column(session: AsyncSession) -> bool:
        result = await session.execute(
            text("""
                SELECT EXISTS (
                    SELECT 1
                    FROM information_schema.columns
                    WHERE table_schema = 'public'
                      AND table_name = 'uqs_tenants'
                      AND column_name = 'admin_role'
                )
            """)
        )
        return bool(result.scalar())

    async with get_db_session() as session:
        has_admin_role = await _has_admin_role_column(session)
        if has_admin_role:
            await session.execute(
                text("""
                    INSERT INTO uqs_tenants
                      (id, name, supabase_url, anon_key, service_key, db_url, contact_email, admin_role, active)
                    VALUES
                      (:id, :name, :supabase_url, :anon_key, :service_key, :db_url, :email, :admin_role, true)
                    ON CONFLICT (id) DO NOTHING;
                """),
                {
                    "id": tenant_id,
                    "name": name,
                    "supabase_url": supabase_url,
                    "anon_key": anon_key,
                    "service_key": service_key,
                    "db_url": db_url,
                    "email": contact_email,
                    "admin_role": admin_role,
                },
            )
        else:
            await session.execute(
                text("""
                    INSERT INTO uqs_tenants
                      (id, name, supabase_url, anon_key, service_key, db_url, contact_email, active)
                    VALUES
                      (:id, :name, :supabase_url, :anon_key, :service_key, :db_url, :email, true)
                    ON CONFLICT (id) DO NOTHING;
                """),
                {
                    "id": tenant_id,
                    "name": name,
                    "supabase_url": supabase_url,
                    "anon_key": anon_key,
                    "service_key": service_key,
                    "db_url": db_url,
                    "email": contact_email,
                },
            )
        await session.commit()

    log.info("Tenant registered: id=%s name=%s", tenant_id, name)
    return {"tenant_id": tenant_id, "name": name}


async def get_tenant_info(tenant_id: str) -> Optional[dict]:
    """Get public info about a tenant (safe to return to frontend)."""
    async with get_db_session() as session:
        result = await session.execute(
            text("""
                SELECT id, name, supabase_url, contact_email, created_at
                FROM uqs_tenants
                WHERE id = :tid AND active = true
            """),
            {"tid": tenant_id},
        )
        row = result.fetchone()

    if not row:
        return None

    return {
        "tenant_id": row[0],
        "name": row[1],
        "supabase_url": row[2],
        "contact_email": row[3],
        "created_at": str(row[4]),
    }


async def list_tenants() -> list[dict]:
    """List all active tenants (admin only)."""
    async with get_db_session() as session:
        result = await session.execute(text("""
            SELECT id, name, contact_email, created_at
            FROM uqs_tenants
            WHERE active = true
            ORDER BY created_at DESC;
        """))
        rows = result.fetchall()

    return [
        {"tenant_id": row[0], "name": row[1], "contact_email": row[2], "created_at": str(row[3])}
        for row in rows
    ]


async def get_tenant_auth_info(tenant_id: str) -> Optional[dict]:
    """Get internal auth info for a tenant (Supabase URL and anon_key)."""
    async with get_db_session() as session:
        exists_result = await session.execute(
            text("""
                SELECT EXISTS (
                    SELECT 1
                    FROM information_schema.columns
                    WHERE table_schema = 'public'
                      AND table_name = 'uqs_tenants'
                      AND column_name = 'admin_role'
                )
            """)
        )
        has_admin_role = bool(exists_result.scalar())

        if has_admin_role:
            result = await session.execute(
                text("""
                    SELECT supabase_url, anon_key, admin_role
                    FROM uqs_tenants
                    WHERE id = :tid AND active = true
                """),
                {"tid": tenant_id},
            )
            row = result.fetchone()
        else:
            result = await session.execute(
                text("""
                    SELECT supabase_url, anon_key
                    FROM uqs_tenants
                    WHERE id = :tid AND active = true
                """),
                {"tid": tenant_id},
            )
            base_row = result.fetchone()
            row = (base_row[0], base_row[1], "admin") if base_row else None

    if not row:
        return None

    return {
        "supabase_url": row[0],
        "anon_key": row[1],
        "admin_role": row[2] or "admin",
    }
