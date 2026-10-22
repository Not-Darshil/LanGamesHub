"""Serve the compiled React app so guests need only a browser and the LAN URL.

Hashed files under /assets are cached aggressively; every other unknown GET path
falls back to index.html so client-side routes survive a refresh. API and
WebSocket prefixes are never answered with the SPA shell.
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, Response
from fastapi.staticfiles import StaticFiles

logger = logging.getLogger(__name__)

RESERVED_PREFIXES = ("api", "ws")

NOT_BUILT_PAGE = """<!doctype html><html><head><meta charset="utf-8">
<title>LanGamesHub</title></head><body style="font-family:sans-serif">
<p>The LanGamesHub frontend has not been built on this host.</p></body></html>"""


def mount_frontend(app: FastAPI, dist_dir: Path) -> None:
    index_file = dist_dir / "index.html"
    if not index_file.is_file():
        logger.warning("Frontend build not found at %s; serving placeholder page", dist_dir)

        @app.get("/{full_path:path}", include_in_schema=False)
        def frontend_not_built(full_path: str) -> Response:
            _reject_reserved(full_path)
            return HTMLResponse(NOT_BUILT_PAGE, status_code=503)

        return

    dist_root = dist_dir.resolve()
    assets_dir = dist_root / "assets"
    if assets_dir.is_dir():
        app.mount("/assets", _ImmutableStaticFiles(directory=assets_dir), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str) -> Response:
        _reject_reserved(full_path)
        candidate = (dist_root / full_path).resolve()
        # Serve real top-level files (favicon etc.) only from inside dist.
        if full_path and candidate.is_file() and candidate.is_relative_to(dist_root):
            return FileResponse(candidate)
        return FileResponse(index_file, headers={"Cache-Control": "no-cache"})


def _reject_reserved(full_path: str) -> None:
    first_segment = full_path.split("/", 1)[0]
    if first_segment in RESERVED_PREFIXES:
        raise HTTPException(status_code=404, detail="Not Found")


class _ImmutableStaticFiles(StaticFiles):
    async def get_response(self, path: str, scope):  # type: ignore[override]
        response = await super().get_response(path, scope)
        if response.status_code == 200:
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        return response
