"""
Supabase / PostgreSQL async database connection.
Uses asyncpg under SQLAlchemy 2.0 for async ORM support.
Direct supabase-py client also exposed for convenience.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase
import ssl
from supabase import Client, create_client

from backend.config import settings


# ── SQLAlchemy Async Engine ───────────────────────────────────────────────────

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker | None = None


def get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        if not settings.database_url:
            raise RuntimeError(
                "DATABASE_URL is not set. Add it to your .env file."
            )
        
        db_url = settings.database_url
        if db_url.startswith("postgresql://"):
            db_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)
        
        # Supavisor (Supabase Pooler) + asyncpg requires SNI.
        # We strip ssl from URL and apply a native SSL context.
        if "?" in db_url:
            db_url = db_url.split("?")[0]

        ssl_ctx = ssl.create_default_context()
        ssl_ctx.check_hostname = False
        ssl_ctx.verify_mode = ssl.CERT_NONE

        _engine = create_async_engine(
            db_url,
            connect_args={
                "ssl": ssl_ctx,
                "prepared_statement_cache_size": 0,
                "statement_cache_size": 0,
            },
            echo=settings.debug,
            pool_pre_ping=True,
            pool_size=5,
            max_overflow=10,
        )
    return _engine


def get_session_factory() -> async_sessionmaker:
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
        )
    return _session_factory


@asynccontextmanager
async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Async context manager for a database session."""
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


# ── Supabase JS-style Client (for storage, realtime, etc.) ────────────────────

_supabase_client: Client | None = None


def get_supabase_client() -> Client:
    global _supabase_client
    if _supabase_client is None:
        if not settings.supabase_url or not settings.supabase_anon_key:
            raise RuntimeError(
                "SUPABASE_URL and SUPABASE_ANON_KEY must be set in .env"
            )
        _supabase_client = create_client(
            settings.supabase_url, settings.supabase_anon_key
        )
    return _supabase_client


# ── SQLAlchemy Base ───────────────────────────────────────────────────────────

class Base(DeclarativeBase):
    """Base class for all ORM models."""
    pass


# ── Health check ──────────────────────────────────────────────────────────────

async def ping_database() -> bool:
    """Returns True if database is reachable."""
    try:
        from sqlalchemy import text
        async with get_db_session() as session:
            await session.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
