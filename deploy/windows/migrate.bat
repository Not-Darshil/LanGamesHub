@echo off
rem Apply database migrations (creates/updates LanGamesHub tables in DATABASE_URL).
setlocal
call "%~dp0_common.bat" || exit /b 1
cd /d "%LGH_BACKEND%"
"%LGH_PY%" -m alembic upgrade head
if errorlevel 1 (echo ERROR: migration failed & exit /b 1)
echo Database is up to date.
endlocal
