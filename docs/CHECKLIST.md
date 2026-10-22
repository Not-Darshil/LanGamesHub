# LanGamesHub Development Checklist

Status key: `[x]` done and tested · `[~]` done, verified only partially (see note) · `[ ]` not done

## Phase 1: Foundation
- [x] Repository inspected (empty apart from README games list)
- [x] FastAPI backend (Python 3.11) and React + Vite + TypeScript frontend
- [x] `.env` loading (pydantic-settings, BOM/CRLF tolerant) and `.env.example` documenting every setting
- [x] PostgreSQL via SQLAlchemy 2.x (sync engine, for Windows event-loop compatibility); Alembic migrations 0001–0004
- [x] Logging shared with Uvicorn; `/api/health` and `/api/health/ready`
- [x] Production static serving with SPA fallback, `/api` and `/ws` excluded, protected against path traversal

## Phase 2: Authentication and administration
- [x] Shared room password (argon2 hash or plaintext) → pending request → live host notification
- [x] Admin accounts (argon2), bootstrap from `.env` without overwriting existing accounts
- [x] Approve / reject, rejection enforced on every REST/WS path, including after reconnect
- [x] Nicknames (guest picks once, host can rename), observed IP, connection status, current room
- [x] Session expiry (sliding for players), revocation, disconnection, rate limits, CSRF/origin checks
- [x] Host player identity separate from admin authorization

## Phase 3: Lobby and room management
- [x] Lobby with room summaries only; room details and game state only for members
- [x] Room state machine CREATED → WAITING_FOR_PLAYERS ⇄ READY_TO_START → IN_PROGRESS → COMPLETED / CANCELLED, plus lock, cancel, remove
- [x] Explicit host Start required; READY never auto-starts; start requires every member to be connected
- [x] Row-locked transactions; concurrency tests for joins and starts
- [x] Disconnect grace (READY → WAITING), forfeits on leave/revoke, match history

## Phase 4: Guest Screen Hide
- [x] Server-side per-session `VISIBLE`/`HIDDEN`, admin-only, idempotent
- [x] Pushed over the authenticated WebSocket; hidden sessions receive no lobby, room, game or name data
- [x] Enforced on refresh, reconnect and server restart; game state and turns unaffected

## Phase 5: Games (rules in docs/games/)
- [x] UNO: challengeable Wild Draw Four, UNO call/catch, single hand
- [x] Snakes and Ladders: server dice, exact roll to finish
- [x] Ludo: 6 to leave the yard, three-sixes forfeit, safe squares, captures, exact home
- [x] Battleship: secret placement, fleet never disclosed to the opponent
- [x] Chess: python-chess legality, castling, en passant, promotion, every draw type, resign

Each game has an engine with rule and randomized/fuzz tests, an API integration test, a UI component, and a browser E2E bot.

## Phase 6: Offline packaging and hardening
- [x] `scripts/build-bundle.sh`: frontend build (checked for remote URLs), pinned wheelhouse (sdist-only `chess` built into a universal wheel), offline-resolvability check, manifest, zip
- [x] Windows wheelhouse resolves completely for win_amd64 / CPython 3.11 with `--no-index`
- [x] Offline install rehearsed end to end (macOS wheels, same bundle and procedure): `pip --no-index` with proxies blocked, fresh DB, migrate, diagnose, start, E2E 42/42, zero external requests, no non-local sockets, backup
- [x] CLI: diagnose, hash-password, set-admin-password, backup, restore (confirmation required); pg_dump/pg_restore round trip tested
- [x] Hardening: CSP (self only), security headers, 64 KB body limit, WebSocket message limit and per-session socket cap
- [~] Windows `.bat` scripts (install, migrate, start, diagnose, backup, restore, passwords): written and reviewed, **not yet run on Windows**. Their Python commands are the ones exercised in the rehearsal.
- [ ] Run the bundle on the real isolated Windows host (see docs/INSTALL-WINDOWS.md)

## Phase 7: Premium UI and chess clocks
- [x] Dark design system (tokens, motion, reduced-motion support), system fonts only, no new dependencies
- [x] Shared UI: toasts, styled confirm dialogs, avatars, 3D dice, confetti, synthesized sounds with mute, turn alerts
- [x] Redesigned access flow, lobby (room cards, game tiles, propose dialog), waiting room, host dashboard
- [x] All five games redesigned with animations (chess: drag and drop, move animation, captured pieces, board themes)
- [x] Room options (migration 0005) and server-side chess clocks: 1+0, 3+2, 5+0, 10+0, 15+10, 30+0 or none; timeout and timeout-vs-insufficient-material; periodic flag check
- [ ] Re-run the offline bundle rehearsal with this version

## Test results (latest run, 2026-10-23)
- Backend: **531 passed, 4 skipped** (adds chess clock engine and API tests).
- Browser E2E: `node e2e/run.mjs` → **48/48 checks**, all five games plus a timed chess game,
  zero requests to external hosts.

## Test results (2026-10-22)
- Backend: `backend/.venv/bin/python -m pytest` → **518 passed, 4 skipped** (the skips are
  3–4 player contract cases for the two-player games), stable over 3 consecutive runs.
- Browser E2E: `node e2e/run.mjs` → **42/42 checks**, all five games, zero requests to
  external hosts.
- Offline install rehearsal of the bundle (macOS wheels): 42/42 E2E against the
  installed bundle.
- Independent code review: 5 issues found (one high: a game left with one remaining
  player at a non-zero seat broke state pushes). All fixed, with regression tests in
  `tests/test_review_regressions.py` and `tests/games/test_engine_contract.py`.
