@echo off
setlocal EnableExtensions
cd /d "%~dp0"

set "PY="
if exist "venv\Scripts\python.exe" set "PY=venv\Scripts\python.exe"
if not defined PY (
  where py >nul 2>&1 && set "PY=py -3"
)
if not defined PY (
  where python >nul 2>&1 && set "PY=python"
)
if not defined PY (
  echo [ERROR] Python not found. Cannot create the mandatory backup.
  pause
  exit /b 1
)

%PY% "%~dp0scripts\saherbot_uninstall.py" %*
set "ERR=%ERRORLEVEL%"
if %ERR% neq 0 pause
exit /b %ERR%
