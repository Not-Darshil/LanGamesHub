"""Empty every application table in the E2E database. Refuses non-test databases."""

import sys

from sqlalchemy import create_engine, make_url, text

url = sys.argv[1]
name = make_url(url).database or ""
if not name.endswith("_test"):
    sys.exit(f"Refusing to reset {name!r}: E2E only runs against a database ending in _test")
engine = create_engine(url)
with engine.begin() as conn:
    tables = conn.execute(text(
        "SELECT tablename FROM pg_tables WHERE schemaname = current_schema() "
        "AND tablename <> 'alembic_version'")).scalars().all()
    if tables:
        conn.execute(text(f"TRUNCATE {', '.join(tables)} RESTART IDENTITY CASCADE"))
print(f"reset {name}: {len(tables)} tables")
