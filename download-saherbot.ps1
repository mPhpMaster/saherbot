$desktop = [Environment]::GetFolderPath('Desktop')
if (-not (Test-Path $desktop)) { Throw "Desktop folder not found: $desktop" }

$defaultDir = 'saherbot-main'
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

$botToken = Read-Host 'Enter BOT_TOKEN value (leave blank to skip)'
$chatId = Read-Host 'Enter CHAT_ID value (leave blank to skip)'

Set-Location $desktop
$url = 'https://github.com/mPhpMaster/saherbot/archive/refs/heads/main.zip'
$zip = Join-Path $env:TEMP 'saherbot-main.zip'
$extractPath = Join-Path $env:TEMP 'saherbot-extract'

Remove-Item -Recurse -Force $zip,$extractPath -ErrorAction SilentlyContinue
Invoke-WebRequest -Uri $url -OutFile $zip -UseBasicParsing
Expand-Archive -Path $zip -DestinationPath $extractPath -Force
Remove-Item $zip

$rootFolder = Get-ChildItem -Path $extractPath | Where-Object { $_.PSIsContainer } | Select-Object -First 1
if (-not $rootFolder) { Throw "Failed to extract archive to $extractPath" }
Move-Item -Path $rootFolder.FullName -Destination $installDir

Set-Location $installDir
.\install.bat

$envFile = Join-Path $installDir '.env'
if (Test-Path $envFile) {
    $content = Get-Content $envFile -Raw
    if (-not [string]::IsNullOrWhiteSpace($botToken)) {
        $content = [regex]::Replace($content, '^(BOT_TOKEN\s*=).*$', "`$1$botToken", 'Multiline')
    }
    if (-not [string]::IsNullOrWhiteSpace($chatId)) {
        $content = [regex]::Replace($content, '^(CHAT_ID\s*=).*$', "`$1$chatId", 'Multiline')
    }
    Set-Content -Path $envFile -Value $content -Encoding UTF8
    Write-Host "Updated .env with provided values."
} else {
    Write-Host "Warning: .env file not found at $installDir. Please edit it manually after installation."
}
