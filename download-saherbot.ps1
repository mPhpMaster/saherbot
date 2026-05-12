$ErrorActionPreference = 'Stop'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$desktop = [Environment]::GetFolderPath('Desktop')
if (-not (Test-Path $desktop)) { throw "Desktop folder not found: $desktop" }

$repoZipUrl = 'https://github.com/mPhpMaster/saherbot/archive/refs/heads/main.zip'
$defaultDir = 'saherbot'
$installName = Read-Host "Enter installation folder name on Desktop [$defaultDir]"
if ([string]::IsNullOrWhiteSpace($installName)) { $installName = $defaultDir }

$installDir = Join-Path $desktop $installName
if (Test-Path $installDir) {
    $confirm = Read-Host "Directory '$installDir' already exists. Overwrite? (Y/N)"
    if ($confirm -notin 'Y','y') {
        Write-Host 'Installation cancelled.'
        exit 1
    }
    Remove-Item -Recurse -Force $installDir
}

Set-Location $desktop
$zip = Join-Path $env:TEMP 'saherbot-main.zip'
$extractPath = Join-Path $env:TEMP 'saherbot-extract'

Remove-Item -Recurse -Force $zip,$extractPath -ErrorAction SilentlyContinue

Write-Host 'Downloading SaherBot ZIP...'
Invoke-WebRequest -Uri $repoZipUrl -OutFile $zip -UseBasicParsing

Write-Host 'Extracting...'
Expand-Archive -Path $zip -DestinationPath $extractPath -Force
Remove-Item $zip

$rootFolder = Get-ChildItem -Path $extractPath | Where-Object { $_.PSIsContainer } | Select-Object -First 1
if (-not $rootFolder) { throw "Failed to extract archive to $extractPath" }
Move-Item -Path $rootFolder.FullName -Destination $installDir
Remove-Item -Recurse -Force $extractPath -ErrorAction SilentlyContinue

Set-Location $installDir
Write-Host 'Running install.bat...'
cmd /c install.bat
if ($LASTEXITCODE -ne 0) {
    Write-Host "install.bat failed (exit $LASTEXITCODE)."
    exit $LASTEXITCODE
}

$data = Join-Path $installDir 'data'
$backups = Join-Path $installDir 'data\backups'
if (-not (Test-Path $data)) { New-Item -ItemType Directory -Path $data | Out-Null }
if (-not (Test-Path $backups)) { New-Item -ItemType Directory -Path $backups | Out-Null }

Write-Host ""
Write-Host "Done. Project: $installDir"
Write-Host "Set DASHBOARD_PASSWORD in .env if needed, then toggle the dashboard:  ./run.sh"
Write-Host "  (or foreground: ./venv/bin/python3 run_dashboard.py start)"
Write-Host ""
Write-Host "From the dashboard, sign in and start/stop the bot there."
Write-Host "Uninstall scripts create a mandatory backup in data\backups\ before removal."
Write-Host "See SETUP_WITHOUT_GIT.md or DOCUMENTATION.md for details."
