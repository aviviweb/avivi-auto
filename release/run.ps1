param(
    [string]$InstallDir = "$(Join-Path $env:LOCALAPPDATA "Avivi\\ClientApp")",
    [string]$ConfigPath = "$(Join-Path $env:LOCALAPPDATA "Avivi\\update_config.json")"
)

$ErrorActionPreference = "Stop"

function Get-Config() {
    if (Test-Path $ConfigPath) {
        try { return (Get-Content -Raw -Path $ConfigPath | ConvertFrom-Json -AsHashtable) } catch { }
    }
    return @{}
}

$cfg = Get-Config
$zipUrl = ($cfg["zip_url"] | ForEach-Object { $_.ToString() })
$shaUrl = ($cfg["sha256_url"] | ForEach-Object { $_.ToString() })

if ($zipUrl -and $shaUrl) {
    try {
        $updateScript = Join-Path $PSScriptRoot "update.ps1"
        if (-not (Test-Path $updateScript)) {
            $updateScript = Join-Path (Join-Path $env:LOCALAPPDATA "Avivi") "update.ps1"
        }
        if (Test-Path $updateScript) {
            powershell -NoProfile -ExecutionPolicy Bypass -File $updateScript -ZipUrl $zipUrl -Sha256Url $shaUrl -InstallDir $InstallDir -Silent
        }
    } catch {
        # Don't block app startup on update errors
    }
}

# Launch app
$appFolder = Join-Path $InstallDir "AviviClient"
$exe = Join-Path $appFolder "AviviClient.exe"
if (-not (Test-Path $exe)) {
    $exe = Join-Path $InstallDir "AviviClient.exe"
    $appFolder = $InstallDir
}
if (Test-Path $exe) {
    Start-Process -FilePath $exe -WorkingDirectory $appFolder
}

