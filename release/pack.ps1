param(
    [string]$DistFolder = "",
    [string]$OutZip = ""
)

$ErrorActionPreference = "Stop"

if (-not $DistFolder) {
    $DistFolder = Join-Path $PSScriptRoot "..\\dist\\AviviClient"
    $DistFolder = (Resolve-Path $DistFolder).Path
}
if (-not $OutZip) {
    $OutZip = Join-Path $PSScriptRoot "AviviClient.zip"
}

if (-not (Test-Path $DistFolder)) {
    throw "Dist folder not found: $DistFolder. Build first (packaging\\build.ps1)."
}

if (Test-Path $OutZip) {
    Remove-Item -Force $OutZip
}

$tmp = Join-Path ([System.IO.Path]::GetTempPath()) ("avivi-client-zip-" + [guid]::NewGuid().ToString("n"))
New-Item -ItemType Directory -Path $tmp | Out-Null

try {
    Copy-Item -Recurse -Force -Path $DistFolder -Destination (Join-Path $tmp "AviviClient")
    Compress-Archive -Path (Join-Path $tmp "AviviClient") -DestinationPath $OutZip -CompressionLevel Optimal
    Write-Host "Created: $OutZip"
} finally {
    Remove-Item -Recurse -Force $tmp -ErrorAction SilentlyContinue
}

