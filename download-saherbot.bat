@echo off
setlocal EnableDelayedExpansion

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

set /p "botToken=Enter BOT_TOKEN value (leave blank to skip): "
set /p "chatId=Enter CHAT_ID value (leave blank to skip): "

cd /d "%desktop%"
set "url=https://github.com/mPhpMaster/saherbot/archive/refs/heads/main.zip"
set "zip=%TEMP%\saherbot-main.zip"
set "extractPath=%TEMP%\saherbot-extract"

if exist "%zip%" del "%zip%"
if exist "%extractPath%" rmdir /s /q "%extractPath%"

powershell -NoProfile -Command "Invoke-WebRequest -Uri '%url%' -OutFile '%zip%' -UseBasicParsing"
if errorlevel 1 (
    echo Failed to download the archive.
    pause
    exit /b 1
)

powershell -NoProfile -Command "Expand-Archive -Path '%zip%' -DestinationPath '%extractPath%' -Force"
if errorlevel 1 (
    echo Failed to extract the archive.
    del "%zip%"
    pause
    exit /b 1
)

del "%zip%"

for /d %%i in ("%extractPath%\*") do (
    move "%%i" "%installDir%"
    goto :moved
)
echo Failed to find extracted folder.
pause
exit /b 1

:moved
cd /d "%installDir%"
call install.bat

set "envFile=%installDir%\.env"
if exist "%envFile%" (
    if not "%botToken%"=="" (
        powershell -NoProfile -Command "(Get-Content '%envFile%') -replace '^(BOT_TOKEN\s*=).*$', '$1%botToken%' | Set-Content '%envFile%' -Encoding UTF8"
    )
    if not "%chatId%"=="" (
        powershell -NoProfile -Command "(Get-Content '%envFile%') -replace '^(CHAT_ID\s*=).*$', '$1%chatId%' | Set-Content '%envFile%' -Encoding UTF8"
    )
    echo Updated .env with provided values.
) else (
    echo Warning: .env file not found at %installDir%. Please edit it manually after installation.
)

pause
exit /b 0