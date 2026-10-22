"""Database engine, session factory, and declarative base.

Synchronous SQLAlchemy is used deliberately: psycopg's async mode is incompatible
with the ProactorEventLoop that asyncio uses by default on Windows. FastAPI runs
sync dependencies in a threadpool, and async code calls DB helpers via
``run_in_threadpool``.
"""

from __future__ import annotations

from functools import lru_cache

from sqlalchemy import Engine, MetaData, create_engine, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import DatabaseSettings, get_database_settings

# Deterministic constraint names keep Alembic autogenerate diffs stable.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def make_engine(settings: DatabaseSettings) -> Engine:
    return create_engine(
        settings.database_url.get_secret_value(),
        pool_pre_ping=True,
        pool_size=10,
        max_overflow=20,
        connect_args={"connect_timeout": 5},
    )


def make_sessionmaker(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False)


@lru_cache
def get_engine() -> Engine:
    """Process-wide engine for CLI tools and Alembic. The web app owns its own."""
    return make_engine(get_database_settings())


def check_database(engine: Engine) -> str | None:
    """Return the current Alembic revision, or None if migrations were never applied.

    Raises if the database is unreachable.
    """
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
        has_version_table = conn.execute(
            text("SELECT to_regclass('alembic_version') IS NOT NULL")
        ).scalar_one()
        if not has_version_table:
            return None
        return conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
