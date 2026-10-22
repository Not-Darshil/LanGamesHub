@echo off
rem Offline install: creates backend\.venv and installs every package from .\wheelhouse.
rem Requires an existing Python 3.11 (x64). Nothing is downloaded.
setlocal
set "LGH_ROOT=%~dp0.."
for %%I in ("%LGH_ROOT%") do set "LGH_ROOT=%%~fI"
cd /d "%LGH_ROOT%"

set "PY="
py -3.11 -c "import sys" >nul 2>nul && set "PY=py -3.11"
if not defined PY (
  python -c "import sys; sys.exit(0 if sys.version_info[:2] == (3, 11) else 1)" >nul 2>nul && set "PY=python"
)
if not defined PY (
  echo ERROR: Python 3.11 was not found. Install Python 3.11 ^(64-bit^) and run this again.
  exit /b 1
)
echo Using %PY%

if not exist "backend\.venv\Scripts\python.exe" (
  echo Creating virtual environment...
  %PY% -m venv "backend\.venv" || (echo ERROR: could not create the virtual environment & exit /b 1)
)

echo Installing packages from the local wheelhouse ^(offline^)...
"backend\.venv\Scripts\python.exe" -m pip install --no-index --find-links "%LGH_ROOT%\wheelhouse" ^
  --require-virtualenv --disable-pip-version-check -r "backend\requirements-windows.txt"
if errorlevel 1 (echo ERROR: package installation failed & exit /b 1)

if not exist ".env" (
  copy ".env.example" ".env" >nul
  echo Created .env from .env.example. Edit it ^(DATABASE_URL, ROOM_PASSWORD, ADMIN_PASSWORD^) before starting.
)
echo.
echo Install complete. Next: edit .env, then run migrate.bat, diagnose.bat and start.bat.
endlocal
