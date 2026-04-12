"""
UQS FastAPI Application — Main Entrypoint

Startup sequence:
  1. Initialize Supabase connection
  2. Load RBAC schema cache
  3. Setup cron jobs (if enabled)
  4. Mount all API routers
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.admin import router as admin_router
from backend.api.documents import router as documents_router
from backend.api.query import router as query_router
from backend.api.schema_api import router as schema_router
from backend.config import settings
from backend.core.database import ping_database
from backend.core.logger import AuditEvent, system_logger


# ── Lifespan (startup/shutdown) ───────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup ─────────────────────────────────────────────────────────────
    system_logger.log(AuditEvent.AUTH_SUCCESS, details={"message": "UQS starting up..."})

    # Ping database
    db_ok = await ping_database()
    system_logger.log(
        AuditEvent.AUTH_SUCCESS if db_ok else AuditEvent.ERROR,
        details={"component": "database", "status": "connected" if db_ok else "FAILED"},
    )

    # Setup cron jobs if enabled
    if settings.cron_enabled:
        from backend.cache.cron_generator import setup_cron_jobs
        setup_cron_jobs(app)

    yield

    # ── Shutdown ─────────────────────────────────────────────────────────────
    system_logger.log(AuditEvent.AUTH_SUCCESS, details={"message": "UQS shutting down."})


# ── App Factory ───────────────────────────────────────────────────────────────

def create_app() -> FastAPI:
    app = FastAPI(
        title="Universal Query Solver (UQS)",
        description=(
            "AI-Driven Data Warehouse & Business Intelligence Platform. "
            "Ask natural language questions about your enterprise data."
        ),
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    # ── CORS ─────────────────────────────────────────────────────────────────
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000", "http://localhost:3001"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Routers ───────────────────────────────────────────────────────────────
    app.include_router(query_router)
    app.include_router(documents_router)
    app.include_router(admin_router)
    app.include_router(schema_router)

    # ── Health check ──────────────────────────────────────────────────────────
    @app.get("/health", tags=["system"])
    async def health() -> dict:
        db_ok = await ping_database()
        return {
            "status": "healthy" if db_ok else "degraded",
            "version": "1.0.0",
            "database": "connected" if db_ok else "unreachable",
            "llm_provider": settings.llm_provider,
            "llm_model": settings.llm_model,
        }

    # ── Dev token generator (REMOVE IN PRODUCTION) ────────────────────────────
    if settings.debug:
        from backend.core.auth import create_access_token

        @app.post("/dev/token", tags=["dev"], include_in_schema=True)
        async def dev_token(user_id: str = "u001", role: str = "admin", email: str = "dev@uqs.local") -> dict:
            """
            [DEV ONLY] Generate a test JWT token.
            Remove this endpoint before deploying to production!
            """
            token = create_access_token(user_id=user_id, role=role, email=email)
            return {"access_token": token, "token_type": "bearer", "role": role}

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "backend.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.debug,
    )
