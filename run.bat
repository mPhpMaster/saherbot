@echo off
REM SaherBot - single Windows helper for the dashboard: toggle background on/off
REM and open the dashboard URL in the default browser when the server is running.
REM Bot alone (dev):    venv\Scripts\python.exe main.py
REM Foreground UI:      venv\Scripts\python.exe run_dashboard.py start
setlocal EnableDelayedExpansion
cd /d "%~dp0"

if exist "venv\Scripts\python.exe" (
  set "SB_PY=venv\Scripts\python.exe"
) else (
  set "SB_PY=python"
)

"!SB_PY!" run_dashboard.py toggle
set "RC=!ERRORLEVEL!"

REM Read DASHBOARD_HOST / DASHBOARD_PORT from .env (defaults: 127.0.0.1 / 80).
set "SB_DH=127.0.0.1"
set "SB_DP=80"
if exist ".env" (
  for /f "usebackq tokens=1,* delims==" %%A in (".env") do (
    set "_K=%%A"
    set "_V=%%B"
    if /i "!_K!"=="DASHBOARD_HOST" if not "!_V!"=="" set "SB_DH=!_V!"
    if /i "!_K!"=="DASHBOARD_PORT" if not "!_V!"=="" set "SB_DP=!_V!"
  )
)
REM 0.0.0.0 means "all interfaces"; use localhost for the browser URL.
if "!SB_DH!"=="0.0.0.0" set "SB_DH=127.0.0.1"
if "!SB_DH!"=="" set "SB_DH=127.0.0.1"
if "!SB_DP!"=="" set "SB_DP=80"

REM Give uvicorn a moment to bind before we point the browser at it.
timeout /t 2 /nobreak >nul 2>&1

REM Open the browser only if the dashboard is now running (toggle may have stopped it).
set "SB_STATUS_FILE=%TEMP%\saherbot_dash_status.txt"
"!SB_PY!" run_dashboard.py status > "!SB_STATUS_FILE!" 2>nul
findstr /i "running" "!SB_STATUS_FILE!" >nul
if not errorlevel 1 (
  if "!SB_DP!"=="80" (
    start "" "http://!SB_DH!/"
  ) else (
    start "" "http://!SB_DH!:!SB_DP!/"
  )
)
del "!SB_STATUS_FILE!" >nul 2>&1

endlocal & exit /b %RC%
