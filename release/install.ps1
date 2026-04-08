param(
    [string]$SourceZip = "$(Join-Path $PSScriptRoot "AviviClient.zip")",
    [string]$InstallDir = "$(Join-Path $env:LOCALAPPDATA "Avivi\\ClientApp")",
    [string]$MasterUrl = "",
    [string]$OwnerTelegramToken = "",
    [string]$OwnerTelegramChatId = "",
    [string]$UpdateZipUrl = "",
    [string]$UpdateSha256Url = "",
    [switch]$DesktopShortcut,
    [switch]$Silent
)

$ErrorActionPreference = "Stop"

function Write-Info([string]$msg) {
    Write-Host $msg
}

function Ensure-Directory([string]$path) {
    if (-not (Test-Path $path)) { New-Item -ItemType Directory -Path $path | Out-Null }
}

function Expand-ZipTo([string]$zip, [string]$dest) {
    if (-not (Test-Path $zip)) { throw "Zip not found: $zip" }
    Ensure-Directory $dest
    Expand-Archive -Force -Path $zip -DestinationPath $dest
}

function Merge-JsonFile([string]$path, [hashtable]$updates) {
    $obj = @{}
    if (Test-Path $path) {
        try { $obj = Get-Content -Raw -Path $path | ConvertFrom-Json -AsHashtable } catch { $obj = @{} }
    }
    foreach ($k in $updates.Keys) {
        $v = $updates[$k]
        if ($null -ne $v -and [string]$v -ne "") {
            $obj[$k] = $v
        }
    }
    $json = ($obj | ConvertTo-Json -Depth 8)
    Ensure-Directory (Split-Path -Parent $path)
    Set-Content -Path $path -Value $json -Encoding UTF8
}

function Create-Shortcut([string]$lnkPath, [string]$targetExe, [string]$workDir, [string]$args = "", [string]$icon = "") {
    $wsh = New-Object -ComObject WScript.Shell
    $sc = $wsh.CreateShortcut($lnkPath)
    $sc.TargetPath = $targetExe
    $sc.WorkingDirectory = $workDir
    if ($args) { $sc.Arguments = $args }
    if ($icon) { $sc.IconLocation = $icon }
    $sc.WindowStyle = 1
    $sc.Save()
}

Write-Info "Avivi Client installer (portable)"

if (-not $Silent) {
    Write-Info "InstallDir: $InstallDir"
    Write-Info "SourceZip:  $SourceZip"
}

Ensure-Directory $InstallDir

$backup = ""
if (Test-Path (Join-Path $InstallDir "AviviClient.exe")) {
    $backup = $InstallDir + ".bak-" + (Get-Date -Format "yyyyMMdd-HHmmss")
    Write-Info "Existing install detected. Backing up to: $backup"
    Copy-Item -Recurse -Force -Path $InstallDir -Destination $backup
}

Write-Info "Extracting zip..."
Expand-ZipTo $SourceZip $InstallDir

$appFolder = Join-Path $InstallDir "AviviClient"
$exe = Join-Path $appFolder "AviviClient.exe"
if (-not (Test-Path $exe)) {
    # some zips might contain the folder contents directly
    $exe = Join-Path $InstallDir "AviviClient.exe"
    $appFolder = $InstallDir
}
if (-not (Test-Path $exe)) {
    throw "AviviClient.exe not found after extract. Expected: $exe"
}

$dataDir = Join-Path $env:LOCALAPPDATA "Avivi"
Ensure-Directory $dataDir

# Copy helper scripts to data dir (so Startup can run them)
$installSelf = $MyInvocation.MyCommand.Path
Copy-Item -Force $installSelf (Join-Path $dataDir "install.ps1")
Copy-Item -Force (Join-Path $PSScriptRoot "update.ps1") (Join-Path $dataDir "update.ps1")
Copy-Item -Force (Join-Path $PSScriptRoot "run.ps1") (Join-Path $dataDir "run.ps1")

if ($MasterUrl -or $OwnerTelegramToken -or $OwnerTelegramChatId) {
    $settingsPath = Join-Path $env:LOCALAPPDATA "Avivi\\client_settings.json"
    $updates = @{}
    if ($MasterUrl) { $updates["master_base_url"] = $MasterUrl }
    if ($OwnerTelegramToken) { $updates["owner_telegram_bot_token"] = $OwnerTelegramToken }
    if ($OwnerTelegramChatId) { $updates["owner_telegram_chat_id"] = $OwnerTelegramChatId }
    Merge-JsonFile $settingsPath $updates
    Write-Info "Updated settings: $settingsPath"
}

# Update config for auto-update at startup (optional)
if ($UpdateZipUrl -and $UpdateSha256Url) {
    $cfgPath = Join-Path $dataDir "update_config.json"
    $cfg = @{
        zip_url = $UpdateZipUrl
        sha256_url = $UpdateSha256Url
        updated_at = (Get-Date).ToString("o")
    }
    ($cfg | ConvertTo-Json -Depth 4) | Set-Content -Encoding UTF8 -Path $cfgPath
    Write-Info "Update config saved: $cfgPath"
}

# Startup shortcut
$startupDir = Join-Path $env:APPDATA "Microsoft\\Windows\\Start Menu\\Programs\\Startup"
Ensure-Directory $startupDir
$startupLnk = Join-Path $startupDir "AviviClient.lnk"
Create-Shortcut $startupLnk "$env:SystemRoot\\System32\\WindowsPowerShell\\v1.0\\powershell.exe" $dataDir "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$dataDir\\run.ps1`" -InstallDir `"$InstallDir`"" $exe
Write-Info "Startup shortcut created: $startupLnk"

if ($DesktopShortcut) {
    $desktop = [Environment]::GetFolderPath("Desktop")
    $deskLnk = Join-Path $desktop "AviviClient.lnk"
    Create-Shortcut $deskLnk $exe $appFolder "" $exe
    Write-Info "Desktop shortcut created: $deskLnk"
}

Write-Info "Done."
Write-Info "Run now: `"$exe`""

