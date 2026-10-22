"""Liveness and readiness endpoints.

Responses never include connection details or driver error text; those go to the
server log only, since guests on the LAN can reach these endpoints.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse

from app.api.deps import get_ctx
from app.db import check_database
from app.migrations import head_revision

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/health", tags=["health"])


@router.get("")
def liveness() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/ready")
async def readiness(request: Request) -> JSONResponse:
    expected = head_revision()
    try:
        current = await run_in_threadpool(check_database, get_ctx(request).engine)
    except Exception:
        logger.exception("Readiness check: database unreachable")
        return JSONResponse(
            status_code=503,
            content={"status": "unavailable", "database": "unreachable"},
        )

    migrations_current = current == expected
    body = {
        "status": "ok" if migrations_current else "unavailable",
        "database": "ok",
        "migrations": "current" if migrations_current else "pending",
    }
    if not migrations_current:
        logger.warning("Readiness check: schema at %s, expected %s", current, expected)
    return JSONResponse(status_code=200 if migrations_current else 503, content=body)
