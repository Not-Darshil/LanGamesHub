# LanGamesHub

A self-hosted, offline-first multiplayer gaming platform for Windows PCs on the same
LAN. One Windows PC (the **host**) runs the server; guests play in a browser at the
host's LAN address. Nothing is downloaded at runtime: no internet, cloud service, CDN,
remote font, external login, or Node.js is needed on the host or the guest PCs.

# Games List
1) Uno
1) Snakes and Ladders
1) Ludo
1) Battleship
1) Chess

Rules for each game are documented in [docs/games/](docs/games/). The server enforces
every rule; browsers only send intents ("play card 17") and never game state.

## How it works

* **Guests** open `http://<host-ip>:8000`, enter the shared room password, and wait.
  The host approves or rejects each request live. Approved guests pick a nickname and
  join the lobby. Rejected guests see a plain white page and stay unauthorized on every
  API and WebSocket call.
* **The host** logs in at `http://<host-ip>:8000/admin` (a separate admin account) to
  approve guests, rename/disconnect/revoke players, create and manage rooms, and
  explicitly **start every game**. Rooms never start on their own, even when full and
  ready. The host can also play: "Open player view" gives the host a player identity
  that is separate from the admin login.
* **Guest Screen Hide**: the host can blank one guest's LanGamesHub page (plain white)
  and restore it later. The state is stored server-side, survives refreshes,
  reconnects and server restarts, and only the admin can change it. It affects only
  the LanGamesHub page in that guest's browser; it does not touch the game (no turns
  are skipped), the guest's other applications, or their operating system.

## Runtime dependencies

| Component | Version | Notes |
| --- | --- | --- |
| Windows host | 10/11 x64 | Runs the server |
| Python | 3.11 (64-bit), already installed | `py -3.11` or `python` on PATH |
| PostgreSQL | already installed and running | LanGamesHub needs one database and a role that can create tables in it; server configuration is not modified |
| Python packages | pinned in `backend/requirements-windows.txt` | Installed offline from the bundle's `wheelhouse/` |
| Guest PCs | any modern browser (Edge, Chrome, Firefox) | Nothing to install |

Python packages (all shipped as wheels in the bundle): FastAPI, Starlette, Uvicorn,
websockets, SQLAlchemy 2.x, Alembic, psycopg 3 (binary), pydantic / pydantic-settings,
python-dotenv, argon2-cffi, python-chess, and their transitive dependencies.

## Installing on the host (offline)

Follow **[docs/INSTALL-WINDOWS.md](docs/INSTALL-WINDOWS.md)**. In short:

1. On an internet-connected dev PC: `scripts/build-bundle.sh 1.0.0` → copy
   `dist-bundle/LanGamesHub-1.0.0.zip` to the host and unzip it.
2. On the host: `windows\install.bat` (offline `pip --no-index`), edit `.env`,
   `windows\migrate.bat`, `windows\diagnose.bat`, `windows\start.bat`.
3. Guests open the URL printed by `start.bat` / `diagnose.bat`.

Backups, restores, password resets, upgrades and troubleshooting are in
**[docs/OPERATIONS.md](docs/OPERATIONS.md)**. The security model is described in
**[docs/SECURITY.md](docs/SECURITY.md)**.

## Configuration

All settings come from `.env` in the LanGamesHub folder (real environment variables
override it). [.env.example](.env.example) documents every setting. The essentials:

| Variable | Purpose |
| --- | --- |
| `DATABASE_URL` | `postgresql+psycopg://USER:PASSWORD@HOST:5432/DB` (required) |
| `ROOM_PASSWORD_HASH` or `ROOM_PASSWORD` | Shared password guests enter (hash preferred) |
| `ADMIN_USERNAME`, `ADMIN_PASSWORD` | Bootstrap admin account, created on first start |
| `BIND_HOST`, `BIND_PORT` | Listen address (`0.0.0.0` = reachable from the LAN) and port |
| `PLAYER_SESSION_TTL_MINUTES`, `ADMIN_SESSION_TTL_MINUTES`, `PENDING_REQUEST_TTL_MINUTES` | Session expiry |
| `RATE_LIMIT_*` | Access-request, login and game-action rate limits |
| `LOG_LEVEL`, `FRONTEND_DIST_DIR`, `COOKIE_SECURE` | Logging, built frontend location, cookie flag |

The database URL and passwords never reach the browser.

## What happens when the server restarts

* Sessions, rooms, memberships, readiness, screen-hide state, match history **and the
  full state of every game in progress** are stored in PostgreSQL. Game state is saved
  in the same transaction as each accepted move.
* After a restart, browsers reconnect automatically (with back-off) using their session
  cookies and continue exactly where they were: same hands, boards and turn. Nothing is
  re-dealt or re-rolled.
* Lost on restart (in memory only): live connections (until they reconnect), rate-limit
  counters, and pending disconnect-grace timers. Because start requires every member to
  be connected, a ready room cannot be started until its members have reconnected.
* Pending access requests survive and still expire at their original time.

## Project layout

```
backend/    FastAPI app (app/), Alembic migrations, tests, pinned requirements
frontend/   React + Vite + TypeScript UI (built to frontend/dist, served by FastAPI)
deploy/windows/  Host scripts (install, migrate, start, diagnose, backup, restore, passwords)
docs/       Rules per game, install/operations/security guides, development checklist
e2e/        Browser end-to-end tests (development only)
scripts/    lock-deps.sh (pin dependencies), build-bundle.sh (offline bundle)
```

## Development (internet-connected PC)

Requires Python 3.11, Node.js, [uv](https://docs.astral.sh/uv/), and a PostgreSQL you
can create databases on.

```sh
cp .env.example .env              # set DATABASE_URL, TEST_DATABASE_URL, passwords
cd backend
uv venv --python 3.11 .venv
uv pip install --python .venv/bin/python -r requirements.txt -r requirements-dev.txt
.venv/bin/alembic upgrade head    # migrate DATABASE_URL
.venv/bin/python -m pytest        # unit + integration tests (uses TEST_DATABASE_URL)
.venv/bin/python -m app           # serve API + built frontend on BIND_HOST:BIND_PORT

cd ../frontend
npm install
npm run dev                       # Vite dev server; /api and /ws proxied to :8000
npm run build                     # production build into frontend/dist

cd ../e2e && npm install && cd ..
node e2e/run.mjs                  # browser E2E against TEST_DATABASE_URL (needs a
                                  # Chromium-family browser; set LGH_BROWSER to its path)
```

To change Python dependencies, edit `backend/requirements.in` and run
`scripts/lock-deps.sh`. The server must run as a **single process** (the default):
live connections and rate limits are coordinated in memory.

Development progress and test results are tracked in [docs/CHECKLIST.md](docs/CHECKLIST.md).
