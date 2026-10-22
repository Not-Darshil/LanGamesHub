@echo off
rem Check configuration, database, migrations, frontend build and port; prints guest URLs.
setlocal
call "%~dp0_common.bat" || exit /b 1
cd /d "%LGH_BACKEND%"
"%LGH_PY%" -m app.cli diagnose
endlocal
