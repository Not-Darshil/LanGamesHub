@echo off
rem Print a ROOM_PASSWORD_HASH line for .env, so the room password is not stored in plain text.
setlocal
call "%~dp0_common.bat" || exit /b 1
cd /d "%LGH_BACKEND%"
"%LGH_PY%" -m app.cli hash-password
endlocal
