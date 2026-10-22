@echo off
rem Back up the LanGamesHub database to .\backups (uses pg_dump from the PostgreSQL install;
rem set PG_BIN if it is not found automatically).
setlocal
call "%~dp0_common.bat" || exit /b 1
cd /d "%LGH_BACKEND%"
"%LGH_PY%" -m app.cli backup --out "%LGH_ROOT%\backups"
endlocal
