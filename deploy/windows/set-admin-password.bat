@echo off
rem Create the admin account or change its password (signs out existing admin sessions).
setlocal
call "%~dp0_common.bat" || exit /b 1
cd /d "%LGH_BACKEND%"
"%LGH_PY%" -m app.cli set-admin-password %*
endlocal
