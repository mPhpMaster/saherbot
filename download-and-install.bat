@echo off
setlocal EnableExtensions
cd /d "%~dp0"

set "REPO_ZIP_URL=https://github.com/mPhpMaster/saherbot/archive/refs/heads/main.zip"
set "HERE=%~dp0"
if "%HERE:~-1%"=="\" set "HERE=%HERE:~0,-1%"
set "ZIP=%HERE%\saherbot-repo-temp.zip"
set "ROOT=%HERE%\saherbot-main"

echo.
echo === SaherBot: download ZIP (no Git) and run install ===
echo Target folder: %ROOT%
echo.

where powershell >nul 2>&1
if errorlevel 1 (
  echo [ERROR] PowerShell not found.
  pause
  exit /b 1
)

if exist "%ROOT%" (
  echo Removing old "%ROOT%" ...
  rmdir /s /q "%ROOT%"
  if exist "%ROOT%" (
    echo [ERROR] Could not remove old folder. Close programs using it and retry.
    pause
    exit /b 1
  )
)

if exist "%ZIP%" del /f /q "%ZIP%"

echo Downloading...
powershell -NoProfile -ExecutionPolicy Bypass -Command "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri '%REPO_ZIP_URL%' -OutFile '%ZIP%' -UseBasicParsing"
if errorlevel 1 (
  echo [ERROR] Download failed.
  pause
  exit /b 1
)

echo Extracting...
powershell -NoProfile -ExecutionPolicy Bypass -Command "Expand-Archive -LiteralPath '%ZIP%' -DestinationPath '%HERE%' -Force"
if errorlevel 1 (
  echo [ERROR] Extract failed.
  del /f /q "%ZIP%" 2>nul
  pause
  exit /b 1
)

del /f /q "%ZIP%" 2>nul

if not exist "%ROOT%\install.bat" (
  echo [ERROR] Expected folder not found: %ROOT%
  echo         GitHub may have changed the archive layout; see SETUP_WITHOUT_GIT.md
  pause
  exit /b 1
)

echo Running install...
pushd "%ROOT%"
call install.bat
set "ERR=%ERRORLEVEL%"
popd

echo.
if "%ERR%"=="0" (
  echo Done. Project: %ROOT%
  if not exist "%ROOT%\data" mkdir "%ROOT%\data"
  echo Ensured data\ exists for the dashboard database, PID files, and backups.
  echo Toggle the dashboard ^(on/off in background^):  run.bat
  echo Foreground dashboard:  venv\Scripts\python.exe run_dashboard.py start
  echo.
  echo From the dashboard, sign in and start/stop the bot there.
  echo Uninstall scripts create a mandatory backup in data\backups\ before removal.
  echo Linux/macOS users should use: git clone ... then ./install.sh
) else (
  echo install.bat exited with code %ERR%.
)
pause
exit /b %ERR%
