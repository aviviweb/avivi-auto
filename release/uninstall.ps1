param(
    [string]$InstallDir = "$(Join-Path $env:LOCALAPPDATA "Avivi\\ClientApp")",
    [switch]$PurgeData,
    [switch]$Silent
)

$ErrorActionPreference = "Stop"

function Write-Info([string]$msg) {
    Write-Host $msg
}

function Try-Remove([string]$path) {
    if (Test-Path $path) {
        Remove-Item -Recurse -Force $path -ErrorAction SilentlyContinue
    }
}

if (-not $Silent) {
    Write-Info "Uninstalling Avivi Client (portable)"
}

# Remove Startup shortcut
$startupDir = Join-Path $env:APPDATA "Microsoft\\Windows\\Start Menu\\Programs\\Startup"
$startupLnk = Join-Path $startupDir "AviviClient.lnk"
if (Test-Path $startupLnk) {
    Remove-Item -Force $startupLnk -ErrorAction SilentlyContinue
    Write-Info "Removed Startup shortcut: $startupLnk"
}

# Best-effort: stop running process
try {
    $procs = Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.ProcessName -eq "AviviClient" }
    foreach ($p in $procs) {
        try { Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue } catch {}
    }
} catch {}

# Remove app directory
if (Test-Path $InstallDir) {
    Try-Remove $InstallDir
    Write-Info "Removed install dir: $InstallDir"
}

if ($PurgeData) {
    $dataDir = Join-Path $env:LOCALAPPDATA "Avivi"
    # Don't delete parent if it contains other apps; in this project it's the root data dir.
    Try-Remove $dataDir
    Write-Info "Purged data dir: $dataDir"
} else {
    Write-Info "Data kept in %LOCALAPPDATA%\\Avivi (use -PurgeData to remove)."
}

Write-Info "Done."

