"""FastAPI application factory."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse

from app.api import access, admin, health, rooms, ws
from app.api.deps import CSRF_HEADER, CSRF_VALUE, same_origin
from app.config import Settings, get_settings
from app.context import AppContext
from app.db import check_database, make_engine, make_sessionmaker
from app.frontend import mount_frontend
from app.logging_config import configure_logging
from app.migrations import head_revision
from app.netinfo import guest_urls
from app.realtime.hub import Hub
from app.services import admin_auth
from app.services import rooms as room_service
from app.services.errors import ServiceError
from app.services.views import build_snapshot

logger = logging.getLogger("app")

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
# How often running game clocks are checked for a fallen flag.
CLOCK_CHECK_SECONDS = 0.5
MAX_BODY_BYTES = 64 * 1024
# Everything is served from this host: no CDNs, remote fonts, or third-party scripts.
CONTENT_SECURITY_POLICY = (
    "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data:; font-src 'self'; connect-src 'self' ws: wss:; "
    "object-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'"
)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    ctx: AppContext = app.state.ctx
    if await run_in_threadpool(_check_database_on_startup, ctx):
        outcome = await ctx.run(lambda db: admin_auth.bootstrap_admin(db, ctx.settings))
        if outcome == "missing":
            logger.warning("No admin account %r exists and ADMIN_PASSWORD is not set; "
                           "the dashboard cannot be used until one is created",
                           ctx.settings.admin_username)
    ctx.hub.start()
    clocks = asyncio.create_task(_clock_loop(ctx), name="game-clocks")
    for url in guest_urls(ctx.settings.bind_host, ctx.settings.bind_port):
        logger.info("Guests open %s  ·  host dashboard %s/admin", url, url)
    try:
        yield
    finally:
        clocks.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await clocks
        await ctx.hub.stop()
        ctx.engine.dispose()


async def _clock_loop(ctx: AppContext) -> None:
    """End timed games (chess clocks) whose flag fell while nobody was acting."""
    failing = False
    while True:
        await asyncio.sleep(CLOCK_CHECK_SECONDS)
        try:
            if await ctx.run(room_service.expire_clocks):
                ctx.hub.notify()
            failing = False
        except Exception:
            if not failing:  # log once per outage, not twice a second
                logger.exception("Checking game clocks failed")
            failing = True
            await asyncio.sleep(5)


def _check_database_on_startup(ctx: AppContext) -> bool:
    try:
        current = check_database(ctx.engine)
    except Exception as exc:
        # One line is enough for operators; the full traceback is only useful when debugging.
        logger.error("Database is unreachable at startup; check DATABASE_URL in .env (%s)",
                     getattr(exc, "orig", exc))
        logger.debug("Startup database check failed", exc_info=True)
        return False
    expected = head_revision()
    if current != expected:
        logger.warning(
            "Database schema is at %s but code expects %s; run 'alembic upgrade head'",
            current,
            expected,
        )
        return False
    logger.info("Database connected; schema at revision %s", current)
    return True


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)

    app = FastAPI(
        title="LanGamesHub",
        lifespan=lifespan,
        # Interactive API docs are not needed on guest PCs.
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    engine = make_engine(settings)
    ctx = AppContext(settings=settings, engine=engine, sessions=make_sessionmaker(engine))
    ctx.hub = Hub(
        lambda online, admins: ctx.transaction(lambda db: build_snapshot(db, online, admins)),
        grace_seconds=settings.disconnect_grace_seconds,
    )
    app.state.ctx = ctx

    async def player_went_offline(session_id: int) -> None:
        if await ctx.run(lambda db: room_service.on_player_offline(db, session_id)):
            ctx.hub.notify()

    ctx.hub.offline_callbacks.append(player_went_offline)

    @app.exception_handler(ServiceError)
    async def service_error(request: Request, exc: ServiceError) -> JSONResponse:
        detail = "Not available" if getattr(request.state, "screen_hidden", False) else exc.message
        return JSONResponse(status_code=exc.status_code, content={"detail": detail})

    @app.middleware("http")
    async def csrf_guard(request: Request, call_next):  # noqa: ANN001, ANN202
        # Cookies are SameSite=Strict; additionally require a custom header (which
        # cross-origin pages cannot send without a CORS preflight we never allow)
        # and a matching Origin on every state-changing API call.
        if request.url.path.startswith("/api/") and request.method not in SAFE_METHODS:
            if request.headers.get(CSRF_HEADER) != CSRF_VALUE or not same_origin(request.headers):
                return JSONResponse(status_code=403, content={"detail": "Forbidden"})
            length = request.headers.get("content-length")
            oversized = length is not None and (not length.isdigit() or int(length) > MAX_BODY_BYTES)
            if oversized or request.headers.get("transfer-encoding"):
                return JSONResponse(status_code=413, content={"detail": "Request too large"})
        response = await call_next(request)
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        else:
            response.headers["Content-Security-Policy"] = CONTENT_SECURITY_POLICY
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    app.include_router(health.router)
    app.include_router(access.router)
    app.include_router(admin.router)
    app.include_router(rooms.router)
    app.include_router(ws.router)
    # Must be registered last: its catch-all route would shadow later routes.
    mount_frontend(app, settings.frontend_dist_dir)
    return app
