# Build frozen Avivi Master + Avivi Client (Windows). Run from repo root or this folder.
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
if (-not (Test-Path (Join-Path $Root "pyproject.toml"))) {
    $Root = $PSScriptRoot
}
Set-Location $Root

Write-Host "Installing editable package + PyInstaller..."
python -m pip install -e ".[build]"

Write-Host "Building AviviMaster..."
python -m PyInstaller --clean --noconfirm (Join-Path $Root "packaging\avivi-master.spec")

Write-Host "Building AviviClient..."
python -m PyInstaller --clean --noconfirm (Join-Path $Root "packaging\avivi-client.spec")

$masterDist = Join-Path $Root "dist\AviviMaster"
if (Test-Path $masterDist) {
    Copy-Item -Force (Join-Path $Root "packaging\env.master.example") (Join-Path $masterDist "env.example.txt")
}

Write-Host "Done. Output:"
Write-Host "  Master: $(Join-Path $Root 'dist\AviviMaster\AviviMaster.exe')"
Write-Host "  Client: $(Join-Path $Root 'dist\AviviClient\AviviClient.exe')"
Write-Host "Zip each dist\Avivi* folder for distribution (entire folder is required)."
