"""Host maintenance commands: ``python -m app.cli <command>``.

    diagnose              check configuration, database, migrations, frontend, port
    hash-password         print an argon2 hash for ROOM_PASSWORD_HASH
    set-admin-password    create the admin account or change its password
    backup [--out DIR]    pg_dump the database to a timestamped .dump file
    restore FILE          pg_restore a backup into the configured database
"""

from __future__ import annotations

import argparse
import getpass
import glob
import importlib
import os
import shutil
import socket
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from sqlalchemy import make_url

from app.config import DEFAULT_ENV_FILE, REPO_ROOT

OK, WARN, FAIL = "PASS", "WARN", "FAIL"


def _report(status: str, message: str) -> bool:
    print(f"[{status}] {message}")
    return status != FAIL


# -- diagnose ---------------------------------------------------------------------------


def diagnose(_: argparse.Namespace) -> int:
    ok = True
    version = sys.version_info
    ok &= _report(OK if version[:2] == (3, 11) else WARN,
                  f"Python {version.major}.{version.minor}.{version.micro} "
                  f"({'expected 3.11' if version[:2] != (3, 11) else 'supported'})")
    missing = []
    for module in ("fastapi", "uvicorn", "websockets", "sqlalchemy", "alembic", "psycopg",
                   "argon2", "chess", "pydantic_settings"):
        try:
            importlib.import_module(module)
        except ImportError:
            missing.append(module)
    ok &= _report(FAIL if missing else OK,
                  f"Missing Python packages: {', '.join(missing)} (run install)" if missing
                  else "Required Python packages are installed")

    ok &= _report(OK if DEFAULT_ENV_FILE.is_file() else WARN,
                  f".env {'found' if DEFAULT_ENV_FILE.is_file() else 'not found'} at "
                  f"{DEFAULT_ENV_FILE}")
    try:
        from app.config import get_settings

        settings = get_settings()
    except Exception as exc:  # noqa: BLE001
        _report(FAIL, f"Configuration is invalid: {exc}")
        return 1
    url = make_url(settings.database_url.get_secret_value())
    _report(OK, f"Configuration loaded (database {url.database} on {url.host}:{url.port or 5432})")
    _report(OK if settings.room_password_hash else WARN,
            "Room password stored as a hash" if settings.room_password_hash else
            "Room password is plaintext in .env; consider ROOM_PASSWORD_HASH")

    from app.db import check_database, make_engine
    from app.migrations import head_revision

    engine = make_engine(settings)
    try:
        current = check_database(engine)
    except Exception as exc:  # noqa: BLE001
        ok &= _report(FAIL, f"Cannot connect to PostgreSQL: {getattr(exc, 'orig', exc)}")
        current = "unreachable"
    else:
        _report(OK, "PostgreSQL connection works")
        expected = head_revision()
        ok &= _report(OK if current == expected else FAIL,
                      f"Schema revision {current}; code expects {expected}"
                      + ("" if current == expected else " (run migrate)"))
    if current not in (None, "unreachable"):
        from sqlalchemy import select
        from sqlalchemy.orm import Session

        from app.models import AdminUser

        with Session(engine) as db:
            has_admin = db.scalar(select(AdminUser.id).where(
                AdminUser.username == settings.admin_username)) is not None
        ok &= _report(OK if has_admin or settings.admin_password else FAIL,
                      f"Admin account {settings.admin_username!r} "
                      + ("exists" if has_admin else "will be created on first start"
                         if settings.admin_password else
                         "does not exist and ADMIN_PASSWORD is not set"))
    engine.dispose()

    index = settings.frontend_dist_dir / "index.html"
    ok &= _report(OK if index.is_file() else FAIL,
                  f"Frontend build {'found' if index.is_file() else 'missing'} at "
                  f"{settings.frontend_dist_dir}")

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind((settings.bind_host, settings.bind_port))
            _report(OK, f"Port {settings.bind_port} on {settings.bind_host} is free")
        except OSError as exc:
            _report(WARN, f"Cannot bind {settings.bind_host}:{settings.bind_port} ({exc}); "
                          "is the server already running?")

    from app.netinfo import guest_urls

    for guest_url in guest_urls(settings.bind_host, settings.bind_port):
        print(f"       Guest URL: {guest_url}   Host dashboard: {guest_url}/admin")
    print("All checks passed." if ok else "Some checks FAILED; see above.")
    return 0 if ok else 1


# -- passwords --------------------------------------------------------------------------


def _ask_password(prompt: str, minimum: int) -> str:
    while True:
        first = getpass.getpass(prompt)
        if len(first) < minimum:
            print(f"Use at least {minimum} characters.")
            continue
        if getpass.getpass("Repeat: ") == first:
            return first
        print("The passwords did not match.")


def hash_password_cmd(_: argparse.Namespace) -> int:
    from app.security import hash_password

    password = _ask_password("Room password: ", 4)
    print("\nPut this line in .env (and remove ROOM_PASSWORD):")
    print(f"ROOM_PASSWORD_HASH={hash_password(password)}")
    return 0


def set_admin_password(args: argparse.Namespace) -> int:
    from sqlalchemy.orm import Session

    from app.config import get_settings
    from app.db import make_engine
    from app.services.admin_auth import set_admin_password as set_password

    settings = get_settings()
    username = args.username or settings.admin_username
    password = _ask_password(f"New password for admin {username!r}: ", 8)
    engine = make_engine(settings)
    with Session(engine) as db, db.begin():
        set_password(db, username, password)
    engine.dispose()
    print(f"Password for {username!r} updated. Existing admin sessions were signed out.")
    return 0


# -- backup / restore -------------------------------------------------------------------


def _pg_tool(name: str) -> str:
    exe = f"{name}.exe" if os.name == "nt" else name
    candidates = []
    if os.environ.get("PG_BIN"):
        candidates.append(str(Path(os.environ["PG_BIN"]) / exe))
    if found := shutil.which(name):
        candidates.append(found)
    patterns = [r"C:\Program Files\PostgreSQL\*\bin", "/Library/PostgreSQL/*/bin",
                "/usr/lib/postgresql/*/bin"]
    for pattern in patterns:
        for directory in sorted(glob.glob(pattern), reverse=True):
            candidates.append(str(Path(directory) / exe))
    for candidate in candidates:
        if Path(candidate).is_file():
            return candidate
    raise SystemExit(f"Could not find {exe}. Set PG_BIN to PostgreSQL's bin directory.")


def _connection_args() -> tuple[list[str], dict[str, str]]:
    from app.config import get_database_settings

    url = make_url(get_database_settings().database_url.get_secret_value())
    args = ["-h", url.host or "localhost", "-p", str(url.port or 5432),
            "-U", url.username or "postgres", "-d", url.database or ""]
    env = {**os.environ}
    if url.password:
        env["PGPASSWORD"] = url.password  # passed via environment, never on the command line
    return args, env


def backup(args: argparse.Namespace) -> int:
    out_dir = Path(args.out or REPO_ROOT / "backups")
    out_dir.mkdir(parents=True, exist_ok=True)
    conn, env = _connection_args()
    target = out_dir / f"langameshub-{datetime.now():%Y%m%d-%H%M%S}.dump"
    subprocess.run([_pg_tool("pg_dump"), *conn, "--format=custom", "--no-owner",
                    f"--file={target}"], env=env, check=True)
    print(f"Backup written to {target}")
    return 0


def restore(args: argparse.Namespace) -> int:
    source = Path(args.file)
    if not source.is_file():
        raise SystemExit(f"Backup file not found: {source}")
    conn, env = _connection_args()
    database = conn[conn.index("-d") + 1]
    if not args.yes:
        print(f"This REPLACES all LanGamesHub data in database {database!r} with {source}.")
        print("Stop the server first. Type RESTORE to continue: ", end="", flush=True)
        if input().strip() != "RESTORE":
            print("Cancelled.")
            return 1
    subprocess.run([_pg_tool("pg_restore"), *conn, "--clean", "--if-exists", "--no-owner",
                    "--single-transaction", str(source)], env=env, check=True)
    print("Restore complete. Run diagnose, then start the server.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("diagnose").set_defaults(fn=diagnose)
    sub.add_parser("hash-password").set_defaults(fn=hash_password_cmd)
    admin = sub.add_parser("set-admin-password")
    admin.add_argument("--username")
    admin.set_defaults(fn=set_admin_password)
    b = sub.add_parser("backup")
    b.add_argument("--out", help="directory for the backup file (default: ./backups)")
    b.set_defaults(fn=backup)
    r = sub.add_parser("restore")
    r.add_argument("file")
    r.add_argument("--yes", action="store_true", help="skip the confirmation prompt")
    r.set_defaults(fn=restore)
    args = parser.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
