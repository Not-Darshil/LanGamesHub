@echo off
rem Restore a backup:  restore.bat backups\langameshub-YYYYMMDD-HHMMSS.dump
rem Stop the server first. You will be asked to type RESTORE to confirm.
setlocal
call "%~dp0_common.bat" || exit /b 1
if "%~1"=="" (echo Usage: restore.bat path\to\backup.dump & exit /b 1)
set "BACKUP=%~f1"
cd /d "%LGH_BACKEND%"
"%LGH_PY%" -m app.cli restore "%BACKUP%"
endlocal
