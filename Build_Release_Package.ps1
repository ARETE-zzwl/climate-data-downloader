$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$root = $PSScriptRoot
$versionLine = Select-String -Path (Join-Path $root "pyproject.toml") -Pattern '^version\s*=\s*"([^"]+)"' | Select-Object -First 1
if (-not $versionLine) {
  throw "Cannot read version from pyproject.toml."
}
$version = $versionLine.Matches[0].Groups[1].Value
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$releaseDir = Join-Path $root "release"
$packageName = "ClimateDataDownloader_${version}_windows_${stamp}"
$stage = Join-Path $releaseDir $packageName
$zip = Join-Path $releaseDir "$packageName.zip"

New-Item -ItemType Directory -Force -Path $stage | Out-Null

function Copy-CleanTree {
  param(
    [string]$Source,
    [string]$Destination
  )
  Get-ChildItem -LiteralPath $Source -Recurse -File | Where-Object {
    $_.FullName -notmatch "\\__pycache__\\" -and
    $_.FullName -notmatch "\\[^\\]+\.egg-info\\"
  } | ForEach-Object {
    $relative = $_.FullName.Substring($Source.Length).TrimStart("\", "/")
    $target = Join-Path $Destination $relative
    $targetDir = Split-Path -Parent $target
    New-Item -ItemType Directory -Force -Path $targetDir | Out-Null
    Copy-Item -LiteralPath $_.FullName -Destination $target
  }
}

$items = @(
  "pyproject.toml",
  "README.md",
  "SPEC.md",
  "SPEC_EXTENSION.md"
)

Copy-CleanTree -Source (Join-Path $root "src") -Destination (Join-Path $stage "src")
Copy-CleanTree -Source (Join-Path $root "docs") -Destination (Join-Path $stage "docs")

foreach ($item in $items) {
  $source = Join-Path $root $item
  if (Test-Path $source) {
    Copy-Item -LiteralPath $source -Destination $stage -Recurse
  }
}

Get-ChildItem -LiteralPath $root -Filter "*.bat" | ForEach-Object {
  Copy-Item -LiteralPath $_.FullName -Destination $stage
}

Compress-Archive -Path (Join-Path $stage "*") -DestinationPath $zip

Write-Host "Release package created: $zip"
Write-Host "Note: .venv, .git, downloads, build and dist are not included."
