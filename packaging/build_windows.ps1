<#
================================================================================
  build_windows.ps1  -  Build the no-install portable Windows bundle.

  Produces  dist\AVS_Analytics_Portable.zip  containing:
      Start_AVS_Analytics.bat      (double-click launcher)
      Home.py, app\, sample_data\, .streamlit\
      runtime\                      (private Python 3.11 + all dependencies)

  The end user just extracts the ZIP and double-clicks Start_AVS_Analytics.bat.
  They need NOTHING installed - no Python, Node, Docker, etc.

  Run this once on any Windows machine WITH internet access:
      powershell -ExecutionPolicy Bypass -File packaging\build_windows.ps1

  (This is the only step that needs the internet. The resulting ZIP is fully
   offline and self-contained.)
================================================================================
#>
[CmdletBinding()]
param(
    [string]$PythonVersion = "3.11.9",
    [string]$Port = "8501"
)
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

# Resolve repo root (this script lives in packaging\)
$Root    = Split-Path -Parent $PSScriptRoot
$Build   = Join-Path $Root "packaging\build"
$Dist    = Join-Path $Root "dist"
$Stage   = Join-Path $Build "AVS_Analytics_Portable"
$Runtime = Join-Path $Stage "runtime"

Write-Host "==> AVS Analytics - Windows portable build" -ForegroundColor Cyan
Write-Host "    Repo root : $Root"

# --- Clean staging ----------------------------------------------------------
if (Test-Path $Build) { Remove-Item $Build -Recurse -Force }
New-Item -ItemType Directory -Force -Path $Runtime | Out-Null
New-Item -ItemType Directory -Force -Path $Dist    | Out-Null

# --- 1) Download embeddable Python ------------------------------------------
$embedUrl = "https://www.python.org/ftp/python/$PythonVersion/python-$PythonVersion-embed-amd64.zip"
$embedZip = Join-Path $Build "python-embed.zip"
Write-Host "==> Downloading embeddable Python $PythonVersion" -ForegroundColor Cyan
Invoke-WebRequest -Uri $embedUrl -OutFile $embedZip
Expand-Archive -Path $embedZip -DestinationPath $Runtime -Force

# --- 2) Enable site-packages so pip-installed libs are importable -----------
$pth = Get-ChildItem -Path $Runtime -Filter "python*._pth" | Select-Object -First 1
Write-Host "==> Enabling site-packages in $($pth.Name)" -ForegroundColor Cyan
@"
python311.zip
.
Lib\site-packages
import site
"@ | Set-Content -Path $pth.FullName -Encoding ASCII

# --- 3) Bootstrap pip --------------------------------------------------------
Write-Host "==> Bootstrapping pip" -ForegroundColor Cyan
$getpip = Join-Path $Build "get-pip.py"
Invoke-WebRequest -Uri "https://bootstrap.pypa.io/get-pip.py" -OutFile $getpip
& "$Runtime\python.exe" $getpip --no-warn-script-location

# --- 4) Install dependencies into the private runtime -----------------------
Write-Host "==> Installing dependencies (this can take a few minutes)" -ForegroundColor Cyan
& "$Runtime\python.exe" -m pip install --no-warn-script-location `
    -r (Join-Path $Root "requirements.txt")

# --- 5) Copy application files ----------------------------------------------
Write-Host "==> Copying application files" -ForegroundColor Cyan
Copy-Item (Join-Path $Root "Home.py")       $Stage -Force
Copy-Item (Join-Path $Root "app")           $Stage -Recurse -Force
Copy-Item (Join-Path $Root "sample_data")   $Stage -Recurse -Force
Copy-Item (Join-Path $Root ".streamlit")    $Stage -Recurse -Force
Copy-Item (Join-Path $Root "packaging\Start_AVS_Analytics.bat") $Stage -Force
Copy-Item (Join-Path $Root "README.md")     $Stage -Force -ErrorAction SilentlyContinue

# Strip caches to keep the bundle small
Get-ChildItem -Path $Stage -Include "__pycache__" -Recurse -Directory |
    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue

# --- 6) Zip it up ------------------------------------------------------------
$zip = Join-Path $Dist "AVS_Analytics_Portable.zip"
if (Test-Path $zip) { Remove-Item $zip -Force }
Write-Host "==> Creating $zip" -ForegroundColor Cyan
Compress-Archive -Path "$Stage\*" -DestinationPath $zip

$sizeMB = [math]::Round((Get-Item $zip).Length / 1MB, 1)
Write-Host ""
Write-Host "==> DONE. Portable bundle ready:" -ForegroundColor Green
Write-Host "    $zip  ($sizeMB MB)"
Write-Host "    Ship this ZIP. Users extract it and double-click Start_AVS_Analytics.bat."
