@echo off
rem Shared setup for the LanGamesHub Windows scripts. Not meant to be run directly.
set "LGH_ROOT=%~dp0.."
for %%I in ("%LGH_ROOT%") do set "LGH_ROOT=%%~fI"
set "LGH_BACKEND=%LGH_ROOT%\backend"
set "LGH_PY=%LGH_BACKEND%\.venv\Scripts\python.exe"
if not exist "%LGH_PY%" (
  echo LanGamesHub is not installed yet. Run install.bat first.
  exit /b 1
)
exit /b 0
