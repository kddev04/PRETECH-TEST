@echo off
setlocal
title Pretech Connect
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo   Run setup.bat first.
  pause
  exit /b 1
)
echo.
echo   Pretech Connect
echo   ---------------
echo   Checking MySQL...
".venv\Scripts\python.exe" tools\mysql_docker.py
if errorlevel 1 (
  echo.
  echo   MySQL is not available, so the demo will use a local SQLite file instead.
  echo   Everything works the same; only the database engine differs.
  echo.
  ".venv\Scripts\python.exe" run_demo.py --sqlite
) else (
  ".venv\Scripts\python.exe" run_demo.py
)
echo.
pause
