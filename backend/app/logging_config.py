"""Logging setup shared by the app and Uvicorn so all output uses one format."""

from __future__ import annotations

import logging.config
from typing import Any


def build_logging_config(level: str) -> dict[str, Any]:
    return {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "default": {
                "format": "%(asctime)s %(levelname)-8s [%(name)s] %(message)s",
                "datefmt": "%Y-%m-%d %H:%M:%S",
            },
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "formatter": "default",
                "stream": "ext://sys.stdout",
            },
        },
        "root": {"handlers": ["console"], "level": level},
        "loggers": {
            # Uvicorn installs its own handlers; route them through ours instead.
            "uvicorn": {"handlers": [], "level": level, "propagate": True},
            "uvicorn.error": {"handlers": [], "level": level, "propagate": True},
            "uvicorn.access": {"handlers": [], "level": level, "propagate": True},
            # SQL echo is noisy; only show it when explicitly debugging.
            "sqlalchemy.engine": {"level": "WARNING"},
            "alembic": {"level": "WARNING"},
        },
    }


def configure_logging(level: str) -> None:
    logging.config.dictConfig(build_logging_config(level))
