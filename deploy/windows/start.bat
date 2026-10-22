@echo off
rem Start the LanGamesHub server. Keep this window open; press Ctrl+C to stop.
setlocal
call "%~dp0_common.bat" || exit /b 1
cd /d "%LGH_BACKEND%"
"%LGH_PY%" -m app
endlocal
