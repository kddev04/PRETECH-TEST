@echo off
setlocal
title Pretech Connect - setup
cd /d "%~dp0"
echo.
echo   Pretech Connect - one-time setup
echo   ---------------------------------

set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY ( where python >nul 2>nul && set "PY=python" )
if not defined PY (
  echo   Python is not installed. Install Python 3.10 or newer from https://www.python.org/downloads/
  echo   and tick "Add python.exe to PATH" in the installer, then run setup.bat again.
  goto :fail
)
%PY% -c "import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)" || (
  echo   Python 3.9 or newer is needed. Install a newer Python from https://www.python.org/downloads/
  goto :fail
)

if not exist ".venv\Scripts\python.exe" (
  echo   Creating the Python environment...
  %PY% -m venv .venv || goto :fail
)
echo   Installing libraries (needs internet the first time)...
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -q -r requirements.txt || goto :fail
".venv\Scripts\python.exe" tools\make_env.py || goto :fail

echo.
echo   Setup complete. Next: double-click start-demo.bat
echo.
pause
exit /b 0

:fail
echo.
echo   Setup did not finish. Read the message above.
pause
exit /b 1
