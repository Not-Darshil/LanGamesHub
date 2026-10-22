# Operating LanGamesHub

All scripts live in the bundle's `windows\` folder and use the installed
`backend\.venv`. On a development machine, run the same commands with
`backend/.venv/bin/python -m app.cli <command>` from `backend/`.

## Start and stop

* Start: `windows\start.bat` (keep the window open). The log prints the guest URL.
* Stop: press **Ctrl+C** in that window. Games in progress are already saved; they
  resume after the next start (see "Restart behaviour" in the README).
* Health: `http://<host>:8000/api/health` (process up) and `/api/health/ready`
  (database reachable and migrations current; HTTP 503 otherwise).

## Diagnose

`windows\diagnose.bat` checks the Python version, installed packages, `.env`, the
database connection, the schema revision, the admin account, the frontend build, and
whether the port is free. It prints guest URLs and never prints secrets. It exits
non-zero if anything failed.

## Backups

```bat
windows\backup.bat
```

This writes `backups\langameshub-YYYYMMDD-HHMMSS.dump` (PostgreSQL custom format) using
`pg_dump` from your PostgreSQL install. The tool is found automatically in
`C:\Program Files\PostgreSQL\<version>\bin`; set `PG_BIN` to that folder if needed. The
database password is passed to `pg_dump` through the environment, not the command line.
The backup contains everything: sessions, rooms, game states, match history, and the
admin account (password hash).

Store backups somewhere other than the host's system drive if you can.

## Restore

1. Stop the server.
2. Run `windows\restore.bat backups\langameshub-YYYYMMDD-HHMMSS.dump`.
3. Type `RESTORE` when asked. This **replaces all LanGamesHub tables** in the database
   from `DATABASE_URL` with the backup's contents, in a single transaction (all or
   nothing). Other databases on the server are not touched.
4. Run `windows\diagnose.bat` (and `windows\migrate.bat` if you restored an older
   backup into a newer version), then `windows\start.bat`.

## Passwords

* **Room password**: change `ROOM_PASSWORD_HASH` (from `windows\hash-password.bat`) or
  `ROOM_PASSWORD` in `.env` and restart. Already-approved guests stay approved.
* **Admin password**: `windows\set-admin-password.bat` (or with `--username NAME`). It
  creates the account if it does not exist and signs out every existing admin session.
  `ADMIN_PASSWORD` in `.env` is only used to create the account the first time.

## Session lifetimes

* Pending access requests expire after `PENDING_REQUEST_TTL_MINUTES` (default 15).
* Approved player sessions expire after `PLAYER_SESSION_TTL_MINUTES` (default 720) of
  inactivity; activity extends them.
* Admin sessions expire `ADMIN_SESSION_TTL_MINUTES` (default 480) after login.
* Revoking a player ends their session at once and removes them from their room (it
  forfeits a game in progress).

## Logs

The server logs to the `start.bat` window. Set `LOG_LEVEL=DEBUG` in `.env` for more
detail. Logs include access decisions, admin actions on players and rooms, and game
starts and results. They never include passwords or session tokens.

## Troubleshooting

| Symptom | Check |
| --- | --- |
| `start.bat` says "not installed yet" | Run `windows\install.bat` first |
| "Database is unreachable at startup" | `DATABASE_URL` host, port, user, password; PostgreSQL service running; run `diagnose.bat` |
| "schema is at … but code expects …" | Run `windows\migrate.bat` |
| Guests cannot open the URL | Same network? Firewall rule (INSTALL-WINDOWS.md step 4)? Network profile Private? Use the IP printed by `diagnose.bat` |
| "Too many attempts" for a guest | The rate limit (`RATE_LIMIT_ACCESS_PER_MINUTE`); wait a minute |
| Start game stays disabled | Every member must have joined and pressed "I'm ready", with at least the game's minimum number of players |
| Start game says "Waiting for X to connect" | That player's browser is offline; ask them to reopen the page |
| A guest sees a blank white page | They were rejected or revoked, or the host hid their screen (dashboard shows "hidden"; use Restore Screen) |
| Frontend says "has not been built" | The bundle's `frontend\dist` folder is missing or `FRONTEND_DIST_DIR` is wrong |
