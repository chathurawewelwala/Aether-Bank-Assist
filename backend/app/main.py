"""
Aether Assistant – FastAPI entrypoint.
Async, structured logging, rate limiting, CORS, observability hooks.
"""
from __future__ import annotations

import logging
import os
import sys
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

# Ensure backend is on path when running as script
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.api.routes import router
from app.core.config import get_settings
from app.retrieval.hybrid_store import get_knowledge_store

# Structured logging
structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.add_log_level,
        structlog.processors.JSONRenderer(),
    ],
    wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
)
logger = structlog.get_logger()

settings = get_settings()

# Rate limiting (token-bucket style via slowapi)
limiter = Limiter(key_func=get_remote_address, default_limits=[f"{settings.rate_limit_requests}/minute"])


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("starting_aether_assistant", version=settings.app_version, env=settings.environment)
    if settings.langchain_tracing_v2 and settings.langchain_api_key:
        os.environ["LANGCHAIN_TRACING_V2"] = "true"
        os.environ["LANGCHAIN_API_KEY"] = settings.langchain_api_key
        os.environ["LANGCHAIN_PROJECT"] = settings.langchain_project
        logger.info("langsmith_enabled", project=settings.langchain_project)
    # PostgreSQL schema
    try:
        from app.db.session import init_db
        await init_db()
        logger.info("postgres_ready")
    except Exception as e:
        logger.warning("postgres_init_skipped", error=str(e))
    # Redis ping (optional)
    try:
        from app.memory.redis_store import get_redis
        r = await get_redis()
        logger.info("redis_status", connected=bool(r))
    except Exception as e:
        logger.warning("redis_init_skipped", error=str(e))
    store = get_knowledge_store()
    logger.info("knowledge_store_ready", chunks=len(store.chunks) if store.ready else 0)
    yield
    logger.info("shutting_down")


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="Enterprise AI Assistant for Aether Bank – multi-agent LangGraph, hybrid RAG, RBAC",
    lifespan=lifespan,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix=settings.api_prefix)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.exception("unhandled_error", path=str(request.url.path), error=str(exc))
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error. The request has been logged."},
    )


@app.get("/")
async def root():
    return {
        "service": settings.app_name,
        "company": settings.company_name,
        "version": settings.app_version,
        "docs": "/docs",
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
