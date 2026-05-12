@echo off
setlocal EnableDelayedExpansion

set "REPO_ZIP_URL=https://github.com/mPhpMaster/saherbot/archive/refs/heads/main.zip"
set "desktop=%USERPROFILE%\Desktop"
if not exist "%desktop%" (
    echo Desktop folder not found: %desktop%
    pause
    exit /b 1
)

set "defaultDir=saherbot"
set /p "installName=Enter installation folder name on Desktop [%defaultDir%]: "
if "%installName%"=="" set "installName=%defaultDir%"

set "installDir=%desktop%\%installName%"
if exist "%installDir%" (
    set /p "confirm=Directory '%installDir%' already exists. Overwrite? (Y/N): "
    if /i not "!confirm!"=="Y" (
        echo Installation cancelled.
        pause
        exit /b 1
    )
    rmdir /s /q "%installDir%"
)

cd /d "%desktop%"
set "zip=%TEMP%\saherbot-main.zip"
set "extractPath=%TEMP%\saherbot-extract"

if exist "%zip%" del /f /q "%zip%"
if exist "%extractPath%" rmdir /s /q "%extractPath%"

echo Downloading SaherBot ZIP...
powershell -NoProfile -ExecutionPolicy Bypass -Command "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri '%REPO_ZIP_URL%' -OutFile '%zip%' -UseBasicParsing"
if errorlevel 1 (
    echo Failed to download the archive.
    pause
    exit /b 1
)

echo Extracting...
powershell -NoProfile -ExecutionPolicy Bypass -Command "Expand-Archive -LiteralPath '%zip%' -DestinationPath '%extractPath%' -Force"
if errorlevel 1 (
    echo Failed to extract the archive.
    del /f /q "%zip%" 2>nul
    pause
    exit /b 1
)

del /f /q "%zip%" 2>nul

for /d %%i in ("%extractPath%\*") do (
    move "%%i" "%installDir%"
    goto :moved
)
echo Failed to find extracted folder.
pause
exit /b 1

:moved
rmdir /s /q "%extractPath%" 2>nul

cd /d "%installDir%"
echo Running install.bat...
call install.bat
if errorlevel 1 (
    echo install.bat failed.
    pause
    exit /b 1
)

if not exist "%installDir%\data" mkdir "%installDir%\data"
if not exist "%installDir%\data\backups" mkdir "%installDir%\data\backups"

echo.
echo Done. Project: %installDir%
echo Set DASHBOARD_PASSWORD in .env if needed, then toggle the dashboard:  run.bat
echo   ^(or foreground: venv\Scripts\python.exe run_dashboard.py start^)
echo.
echo From the dashboard, sign in and start/stop the bot there.
echo Uninstall scripts create a mandatory backup in data\backups\ before removal.
echo See SETUP_WITHOUT_GIT.md or DOCUMENTATION.md for details.
pause
exit /b 0
