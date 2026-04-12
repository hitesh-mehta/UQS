"""
UQS FastAPI Application — Main Entrypoint (production-hardened)
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from backend.api.admin import router as admin_router
from backend.api.documents import router as documents_router
from backend.api.query import router as query_router
from backend.api.schema_api import router as schema_router
from backend.config import settings
from backend.core.database import ping_database
from backend.core.logger import AuditEvent, system_logger
from backend.core.security import limiter


# ── Lifespan ───────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    system_logger.log(AuditEvent.AUTH_SUCCESS, details={"message": "UQS starting up..."})

    # Warm up LangGraph pipeline (compiles the graph once)
    from backend.graph.pipeline import get_pipeline
    get_pipeline()
    system_logger.log(AuditEvent.AUTH_SUCCESS, details={"message": "LangGraph pipeline compiled."})

    db_ok = await ping_database()
    system_logger.log(
        AuditEvent.AUTH_SUCCESS if db_ok else AuditEvent.ERROR,
        details={"component": "database", "status": "connected" if db_ok else "FAILED"},
    )

    if settings.cron_enabled:
        from backend.cache.cron_generator import setup_cron_jobs
        setup_cron_jobs(app)

    yield

    system_logger.log(AuditEvent.AUTH_SUCCESS, details={"message": "UQS shutting down."})


# ── App Factory ────────────────────────────────────────────────────────────────
def create_app() -> FastAPI:
    app = FastAPI(
        title="Universal Query Solver (UQS)",
        description=(
            "AI-Driven BI Platform — Ask natural language questions about your data. "
            "Powered by LangGraph, 5 specialized AI engines, RBAC, and smart caching."
        ),
        version="1.0.0",
        docs_url="/docs" if settings.debug else None,
        redoc_url="/redoc" if settings.debug else None,
        lifespan=lifespan,
    )

    # ── Rate Limiter state ────────────────────────────────────────────────────
    app.state.limiter = limiter

    # ── Middleware (order matters — outermost first) ───────────────────────────
    # NOTE: TrustedHost can be strict in CI; relax for dev
    if not settings.debug:
        app.add_middleware(
            TrustedHostMiddleware,
            allowed_hosts=["*"],  # Tighten in production with real domain
        )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000", "http://localhost:3001"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.add_middleware(SlowAPIMiddleware)

    # ── Global exception handlers ─────────────────────────────────────────────
    @app.exception_handler(RateLimitExceeded)
    async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
        return JSONResponse(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            content={
                "error": "rate_limit_exceeded",
                "detail": f"Too many requests. Limit: {settings.rate_limit_per_minute} req/min.",
                "retry_after": "60s",
            },
        )

    @app.exception_handler(Exception)
    async def global_error_handler(request: Request, exc: Exception):
        system_logger.error(f"Unhandled exception: {exc}", exc_info=True)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "error": "internal_error",
                "detail": "An unexpected error occurred. Please try again.",
            },
        )

    # ── Routers ───────────────────────────────────────────────────────────────
    app.include_router(query_router)
    app.include_router(documents_router)
    app.include_router(admin_router)
    app.include_router(schema_router)

    # ── Health ────────────────────────────────────────────────────────────────
    @app.get("/health", tags=["system"])
    async def health() -> dict:
        db_ok = await ping_database()
        return {
            "status": "healthy" if db_ok else "degraded",
            "version": "1.0.0",
            "database": "connected" if db_ok else "unreachable",
            "llm_provider": settings.llm_provider,
            "llm_model": settings.llm_model,
            "pipeline": "langgraph",
        }

    # ── Dev token (debug only) ────────────────────────────────────────────────
    if settings.debug:
        from backend.core.auth import create_access_token

        @app.post("/dev/token", tags=["dev"])
        async def dev_token(
            user_id: str = "u001",
            role: str = "analyst",
            email: str = "dev@uqs.local",
        ) -> dict:
            """[DEV ONLY] Generate a test JWT. Remove before production."""
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
