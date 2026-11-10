"""FastAPI application factory and ASGI entrypoint.

Run locally (from backend/):
    ..\\.venv\\Scripts\\python -m uvicorn app.main:app --reload --port 8000
"""

from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api import agents, applications, bootstrap_tokens, operators, public
from .core.config import get_settings
from .core.db import create_all, session_scope
from .core.errors import install_error_handlers
from .version import VERSION

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)


@asynccontextmanager
async def lifespan(_: FastAPI):
    create_all()
    # Phase 3B: bring the DB to the current shape (additive-only, idempotent).
    from .core.migrations import upgrade_phase3b

    upgrade_phase3b()
    # Seed the approved deployment-template catalog (idempotent).
    from .services.deployments import seed_templates

    with session_scope() as db:
        seed_templates(db)
    yield


def create_app() -> FastAPI:
    settings = get_settings()

    raw_origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
    if "*" in raw_origins:
        raise RuntimeError("NIMBUSOPS_CORS_ORIGINS must not contain '*'; list explicit origins.")

    app = FastAPI(
        title="NimbusOps Control Server",
        version=VERSION,
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=raw_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "Authorization", "X-Host-Id"],
    )

    install_error_handlers(app)
    app.include_router(public.router)
    app.include_router(agents.router)
    app.include_router(applications.router)
    app.include_router(operators.router)
    app.include_router(bootstrap_tokens.router)

    return app


app = create_app()
