"""Entry point: ``python -m app`` starts the server on the configured address."""

from __future__ import annotations

import uvicorn

from app.config import get_settings
from app.logging_config import build_logging_config


def main() -> None:
    settings = get_settings()
    uvicorn.run(
        "app.main:create_app",
        factory=True,
        host=settings.bind_host,
        port=settings.bind_port,
        log_config=build_logging_config(settings.log_level),
        # LAN clients connect directly; there is no reverse proxy to trust.
        proxy_headers=False,
    )


if __name__ == "__main__":
    main()
