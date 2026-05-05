@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0"

echo.
echo === SaherBot - setup (Python + venv + packages) ===
echo.

call :resolve_python
if not defined PYTHON_EXE (
  echo.
  echo [ERROR] Could not find or install Python 3.
  echo - Run this script again after closing and reopening the terminal ^(PATH may update after winget^).
  echo - Or install manually: https://www.python.org/downloads/ ^(enable "Add to PATH"^).
  goto :end_error
)

echo Using: !PYTHON_EXE!
"!PYTHON_EXE!" --version
echo.

echo [1/5] Virtual environment...
if not exist "venv\Scripts\python.exe" (
  "!PYTHON_EXE!" -m venv venv
  if errorlevel 1 (
    echo [ERROR] Could not create venv\. Check that the "venv" module is available.
    goto :end_error
  )
  echo       Created venv\
) else (
  echo       venv\ already exists, skipped.
)

echo [2/5] Upgrading pip...
"venv\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 goto :end_error

echo [3/5] Installing requirements...
"venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (
  echo [ERROR] pip install failed.
  goto :end_error
)

echo [4/5] Folders...
if not exist "logs" mkdir logs
if not exist "list" mkdir list

echo [5/5] Environment file...
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

REM ---------------------------------------------------------------------------
REM Find python.exe: py launcher, common paths, then "python" if not Store stub
REM ---------------------------------------------------------------------------
:resolve_python
set "PYTHON_EXE="
call :try_py_launcher
if defined PYTHON_EXE exit /b 0
call :try_std_paths
if defined PYTHON_EXE exit /b 0
call :try_python_cmd
if defined PYTHON_EXE exit /b 0
call :install_python_winget
if defined PYTHON_EXE exit /b 0
call :try_py_launcher
if defined PYTHON_EXE exit /b 0
call :try_std_paths
if defined PYTHON_EXE exit /b 0
call :try_python_cmd
exit /b 0

:try_py_launcher
where py >nul 2>&1
if errorlevel 1 exit /b 0
for /f "delims=" %%I in ('py -3 -c "import sys; print(sys.executable)" 2^>nul') do (
  set "PYTHON_EXE=%%I"
  exit /b 0
)
exit /b 0

:try_std_paths
for %%V in (314 313 312 311 310) do (
  if exist "!LOCALAPPDATA!\Programs\Python\Python%%V\python.exe" (
    set "PYTHON_EXE=!LOCALAPPDATA!\Programs\Python\Python%%V\python.exe"
    exit /b 0
  )
)
for %%V in (314 313 312 311 310) do (
  if exist "!ProgramFiles!\Python%%V\python.exe" (
    set "PYTHON_EXE=!ProgramFiles!\Python%%V\python.exe"
    exit /b 0
  )
)
exit /b 0

:try_python_cmd
where python >nul 2>&1
if errorlevel 1 exit /b 0
for /f "delims=" %%I in ('where python 2^>nul') do (
  echo %%I | findstr /i "WindowsApps" >nul
  if errorlevel 1 (
    "%%I" -c "import sys" >nul 2>&1
    if not errorlevel 1 (
      set "PYTHON_EXE=%%I"
      exit /b 0
    )
  )
)
exit /b 0

:install_python_winget
echo [0/5] Python not found. Trying winget ^(needs internet; may ask for admin once^)...
where winget >nul 2>&1
if errorlevel 1 (
  echo       winget is not available on this PC.
  exit /b 0
)
winget install -e --id Python.Python.3.12 --accept-package-agreements --accept-source-agreements --disable-interactivity
call :try_std_paths
if not defined PYTHON_EXE call :try_py_launcher
if not defined PYTHON_EXE exit /b 0
for %%P in ("!PYTHON_EXE!") do set "_PYROOT=%%~dpP"
set "_PYROOT=!_PYROOT:~0,-1!"
set "PATH=!_PYROOT!;!_PYROOT!\Scripts;!PATH!"
exit /b 0

:end_error
echo.
pause
exit /b 1

:end_ok
pause
exit /b 0
