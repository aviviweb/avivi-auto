param(
    [string]$ZipUrl = "",
    [string]$Sha256Url = "",
    [string]$InstallDir = "$(Join-Path $env:LOCALAPPDATA "Avivi\\ClientApp")",
    [string]$StatePath = "$(Join-Path $env:LOCALAPPDATA "Avivi\\update_state.json")",
    [switch]$Silent
)

$ErrorActionPreference = "Stop"

function Write-Info([string]$msg) {
    if (-not $Silent) { Write-Host $msg }
}

function Ensure-Directory([string]$path) {
    $p = $path
    if ([IO.Path]::GetExtension($path)) {
        $p = Split-Path -Parent $path
    }
    if ($p -and -not (Test-Path $p)) { New-Item -ItemType Directory -Path $p | Out-Null }
}

function Get-State() {
    if (Test-Path $StatePath) {
        try { return (Get-Content -Raw -Path $StatePath | ConvertFrom-Json -AsHashtable) } catch { }
    }
    return @{}
}

function Set-State([hashtable]$st) {
    Ensure-Directory $StatePath
    ($st | ConvertTo-Json -Depth 6) | Set-Content -Encoding UTF8 -Path $StatePath
}

if (-not $ZipUrl -or -not $Sha256Url) {
    throw "ZipUrl and Sha256Url are required."
}

Write-Info "Checking for update…"
$st = Get-State

$shaText = (Invoke-WebRequest -UseBasicParsing -Uri $Sha256Url -TimeoutSec 20).Content
$remoteSha = (($shaText -split "\s+")[0] | ForEach-Object { $_.Trim().ToLowerInvariant() })
if (-not $remoteSha -or $remoteSha.Length -lt 64) {
    throw "Invalid SHA256 file at $Sha256Url"
}

$localSha = ($st["last_sha256"] | ForEach-Object { $_.ToString().Trim().ToLowerInvariant() })
if ($localSha -and $localSha -eq $remoteSha) {
    Write-Info "Up to date."
    exit 0
}

$tmp = Join-Path ([System.IO.Path]::GetTempPath()) ("avivi-update-" + [guid]::NewGuid().ToString("n"))
New-Item -ItemType Directory -Path $tmp | Out-Null
$zipPath = Join-Path $tmp "AviviClient.zip"

try {
    Write-Info "Downloading update…"
    Invoke-WebRequest -UseBasicParsing -Uri $ZipUrl -OutFile $zipPath -TimeoutSec 120

    $h = (Get-FileHash -Algorithm SHA256 -Path $zipPath).Hash.ToLowerInvariant()
    if ($h -ne $remoteSha) {
        throw "SHA256 mismatch. Expected $remoteSha got $h"
    }

    $installScript = Join-Path $PSScriptRoot "install.ps1"
    if (-not (Test-Path $installScript)) {
        # If running from installed folder, install.ps1 may be alongside run.ps1 in %LOCALAPPDATA%\Avivi\
        $installScript = Join-Path (Join-Path $env:LOCALAPPDATA "Avivi") "install.ps1"
    }
    if (-not (Test-Path $installScript)) {
        throw "install.ps1 not found (needed to apply update)."
    }

    Write-Info "Applying update…"
    powershell -NoProfile -ExecutionPolicy Bypass -File $installScript -SourceZip $zipPath -InstallDir $InstallDir -Silent

    $st["last_sha256"] = $remoteSha
    $st["last_updated_at"] = (Get-Date).ToString("o")
    Set-State $st

    Write-Info "Update applied."
} finally {
    Remove-Item -Recurse -Force $tmp -ErrorAction SilentlyContinue
}

