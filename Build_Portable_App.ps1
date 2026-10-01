param(
  [string]$SignTool = "",
  [string]$CertificateThumbprint = "",
  [switch]$SkipDependencyInstall
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$root = $PSScriptRoot
$python = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
  $py = Get-Command py -ErrorAction SilentlyContinue
  if ($py) {
    & py -3 -m venv (Join-Path $root ".venv")
  } else {
    & python -m venv (Join-Path $root ".venv")
  }
}

if (-not $SkipDependencyInstall) {
  & $python -m pip install --upgrade pip
  if ($LASTEXITCODE -ne 0) { throw "pip upgrade failed." }
  & $python -m pip install ".[build]"
  if ($LASTEXITCODE -ne 0) { throw "Dependency installation failed." }
}

$versionLine = Select-String -Path (Join-Path $root "pyproject.toml") -Pattern '^version\s*=\s*"([^"]+)"' | Select-Object -First 1
if (-not $versionLine) {
  throw "Cannot read version from pyproject.toml."
}
$version = $versionLine.Matches[0].Groups[1].Value
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$releaseDir = Join-Path $root "release"
$workPath = Join-Path $releaseDir "pyinstaller_work_$stamp"
$distPath = Join-Path $releaseDir "pyinstaller_dist_$stamp"
$stage = Join-Path $releaseDir "ClimateDataDownloader_${version}_portable_$stamp"
$zip = "$stage.zip"

New-Item -ItemType Directory -Force -Path $releaseDir | Out-Null

function Invoke-PyInstaller {
  param(
    [string]$Name,
    [switch]$Windowed
  )
  $mode = if ($Windowed) { "--windowed" } else { "--console" }
  & $python -m PyInstaller `
    --noconfirm `
    --clean `
    --onedir `
    $mode `
    --name $Name `
    --distpath $distPath `
    --workpath $workPath `
    --specpath $workPath `
    --paths (Join-Path $root "src") `
    --collect-data certifi `
    --hidden-import scipy._lib.messagestream `
    (Join-Path $root "packaging\pyinstaller_entry.py")
  if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller failed for $Name."
  }
}

function Copy-CleanTree {
  param(
    [string]$Source,
    [string]$Destination
  )
  Get-ChildItem -LiteralPath $Source -Recurse -File | ForEach-Object {
    $relative = $_.FullName.Substring($Source.Length).TrimStart("\", "/")
    $target = Join-Path $Destination $relative
    $targetDir = Split-Path -Parent $target
    New-Item -ItemType Directory -Force -Path $targetDir | Out-Null
    Copy-Item -LiteralPath $_.FullName -Destination $target
  }
}

function Get-TkRuntimeInfo {
  $script = @'
import json
import sys
import tkinter

root = tkinter.Tk()
try:
    payload = {
        "executable": sys.executable,
        "prefix": sys.prefix,
        "base_prefix": sys.base_prefix,
        "tcl_library": root.tk.eval("info library"),
        "tk_library": root.tk.eval("set tk_library"),
        "patchlevel": root.tk.call("info", "patchlevel"),
    }
finally:
    root.destroy()
print(json.dumps(payload))
'@
  return ($script | & $python - | ConvertFrom-Json)
}

function Find-RuntimeDll {
  param(
    [string]$DllName,
    [object]$Runtime
  )
  $candidateRoots = @(
    (Join-Path $Runtime.prefix "DLLs"),
    (Join-Path $Runtime.prefix "Library\bin"),
    (Join-Path $Runtime.base_prefix "DLLs"),
    (Join-Path $Runtime.base_prefix "Library\bin"),
    (Join-Path (Split-Path -Parent (Split-Path -Parent $Runtime.tcl_library)) "bin"),
    (Join-Path (Split-Path -Parent (Split-Path -Parent $Runtime.tk_library)) "bin")
  ) | Select-Object -Unique
  foreach ($candidateRoot in $candidateRoots) {
    $candidate = Join-Path $candidateRoot $DllName
    if (Test-Path $candidate) {
      return $candidate
    }
  }
  throw "Cannot locate $DllName for Tcl/Tk runtime $($Runtime.patchlevel)."
}

function Copy-TkRuntime {
  param(
    [string]$Stage
  )
  $runtime = Get-TkRuntimeInfo
  $internal = Join-Path $Stage "_internal"
  Copy-CleanTree -Source $runtime.tcl_library -Destination (Join-Path $internal "_tcl_data")
  Copy-CleanTree -Source $runtime.tk_library -Destination (Join-Path $internal "_tk_data")
  foreach ($dllName in @("tcl86t.dll", "tk86t.dll")) {
    Copy-Item -LiteralPath (Find-RuntimeDll -DllName $dllName -Runtime $runtime) -Destination $internal -Force
  }
  Write-Host "Bundled Tcl/Tk runtime $($runtime.patchlevel) from $($runtime.tcl_library)."
}

Invoke-PyInstaller -Name "ClimateDataDownloader" -Windowed
Invoke-PyInstaller -Name "ClimateDataDownloaderCLI"

Copy-CleanTree -Source (Join-Path $distPath "ClimateDataDownloader") -Destination $stage
Copy-Item -LiteralPath (Join-Path $distPath "ClimateDataDownloaderCLI\ClimateDataDownloaderCLI.exe") -Destination $stage
Copy-TkRuntime -Stage $stage
Copy-CleanTree -Source (Join-Path $root "docs") -Destination (Join-Path $stage "docs")
Copy-CleanTree -Source (Join-Path $root "examples") -Destination (Join-Path $stage "examples")
Copy-Item -LiteralPath (Join-Path $root "README.md") -Destination $stage

@'
@echo off
cd /d "%~dp0"
start "" "%~dp0ClimateDataDownloader.exe"
'@ | Set-Content -Path (Join-Path $stage "Start_ClimateDataDownloader.bat") -Encoding ASCII

@'
@echo off
cd /d "%~dp0"
"%~dp0ClimateDataDownloaderCLI.exe" batch --config "%~dp0examples\power_batch_small.json" --output "%~dp0downloads\power_batch_small"
pause
'@ | Set-Content -Path (Join-Path $stage "Run_Power_Batch_Demo.bat") -Encoding ASCII

if ($SignTool -and $CertificateThumbprint) {
  & $SignTool sign /fd SHA256 /sha1 $CertificateThumbprint /tr http://timestamp.digicert.com /td SHA256 (Join-Path $stage "ClimateDataDownloader.exe")
  & $SignTool sign /fd SHA256 /sha1 $CertificateThumbprint /tr http://timestamp.digicert.com /td SHA256 (Join-Path $stage "ClimateDataDownloaderCLI.exe")
} else {
  Write-Host "Code signing skipped. Provide -SignTool and -CertificateThumbprint to sign executables."
}

Compress-Archive -Path (Join-Path $stage "*") -DestinationPath $zip
Write-Host "Portable no-Python package created: $zip"
