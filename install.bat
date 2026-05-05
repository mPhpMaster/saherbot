@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0"

echo.
echo === SaherBot - setup ===
echo.

where python >nul 2>&1
if errorlevel 1 (
  echo [ERROR] Python not found. Install Python 3 from https://www.python.org/downloads/
  echo         During setup, enable "Add python.exe to PATH".
  goto :end_error
)

echo [1/4] Virtual environment...
if not exist "venv\Scripts\python.exe" (
  python -m venv venv
  if errorlevel 1 (
    echo [ERROR] Could not create venv\ folder.
    goto :end_error
  )
  echo       Created venv\
) else (
  echo       venv\ already exists, skipped.
)

echo [2/4] Installing packages...
"venv\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 goto :end_error
"venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (
  echo [ERROR] pip install failed.
  goto :end_error
)

echo [3/4] Folders...
if not exist "logs" mkdir logs
if not exist "list" mkdir list

echo [4/4] Environment file...
if not exist ".env" (
  if exist ".env.example" (
    copy /Y ".env.example" ".env" >nul
    echo       Created .env from .env.example
  ) else (
    echo       [WARN] .env.example missing - create .env manually.
  )
) else (
  echo       .env already exists, not overwritten.
)

echo.
echo Setup finished.
echo - Edit .env: set BOT_TOKEN and CHAT_ID ^(use /id in the group as admin^).
echo - Start the bot: run run.bat
echo.
goto :end_ok

:end_error
echo.
pause
exit /b 1

:end_ok
pause
exit /b 0
