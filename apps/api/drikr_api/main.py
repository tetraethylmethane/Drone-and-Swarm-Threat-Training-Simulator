"""Application factory."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from starlette.concurrency import run_in_threadpool

from drikr_api import __version__
from drikr_api.config import Settings, get_settings
from drikr_api.db import Database
from drikr_api.deps import AppContext
from drikr_api.errors import install_error_handlers
from drikr_api.logging_setup import configure_logging
from drikr_api.routers import admin, analytics, assignments, auth, catalog, health, reports, reviews, sessions, users
from drikr_api.security.rate_limit import SlidingWindowLimiter
from drikr_api.services import session_service

log = logging.getLogger("drikr.api")
API_PREFIX = "/api/v1"

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'",
    "Cross-Origin-Resource-Policy": "same-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
}


async def _sweeper(ctx: AppContext) -> None:
    interval = ctx.settings.sweeper_interval_s
    while True:
        await asyncio.sleep(interval)
        try:

            def run() -> int:
                with ctx.database.session_factory() as db:
                    return session_service.sweep(db, ctx.settings.heartbeat_grace_s)

            changed = await run_in_threadpool(run)
            if changed:
                log.info("session_sweep", extra={"sessions_changed": changed})
        except Exception:
            log.exception("session_sweep_failed")


def create_app(settings: Settings | None = None, database: Database | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)
    database = database or Database(settings.database_url)
    ctx = AppContext(
        settings=settings,
        database=database,
        login_limiter=SlidingWindowLimiter(settings.login_rate_limit_per_minute, 60),
    )

    @contextlib.asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        task = asyncio.create_task(_sweeper(ctx)) if settings.sweeper_interval_s > 0 else None
        log.info("startup", extra={"version": __version__, "environment": settings.environment})
        yield
        if task:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
        database.dispose()

    app = FastAPI(
        title="Drikr Systems Training Simulator API",
        version=__version__,
        description="Software-only drone and swarm threat recognition training simulator. All data is synthetic.",
        openapi_url=f"{API_PREFIX}/openapi.json",
        docs_url=None,  # Swagger UI loads assets from a CDN; disabled for offline operation.
        redoc_url=None,
        lifespan=lifespan,
    )
    app.state.ctx = ctx
    install_error_handlers(app)

    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_credentials=True,
            allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
            allow_headers=["Content-Type", "X-CSRF-Token", "Authorization"],
        )

    @app.middleware("http")
    async def request_context(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        rid = request.headers.get("x-request-id") or uuid.uuid4().hex
        rid = rid[:64]
        start = time.perf_counter()
        response = await call_next(request)
        for k, v in SECURITY_HEADERS.items():
            response.headers.setdefault(k, v)
        if request.url.path.startswith("/api"):
            response.headers.setdefault("Cache-Control", "no-store")
        response.headers["X-Request-ID"] = rid
        log.info(
            "request",
            extra={
                "request_id": rid,
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
                "duration_ms": round((time.perf_counter() - start) * 1000, 1),
            },
        )
        return response

    for r in (health, auth, users, catalog, assignments, sessions, reviews, analytics, reports, admin):
        app.include_router(r.router, prefix=API_PREFIX)
    return app


def app_factory() -> FastAPI:
    """Entry point for ``uvicorn --factory drikr_api.main:app_factory``."""
    return create_app()
