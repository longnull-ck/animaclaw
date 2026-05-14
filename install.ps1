# ============================================================
# Anima - Windows Install Script (PowerShell)
# Usage: irm https://raw.githubusercontent.com/longnull-ck/animaclaw/main/install.ps1 | iex
# ============================================================

# When run via 'irm | iex', stdin is consumed by the pipe.
# Fix: download script to temp file and re-execute with proper stdin.
if (-not $env:ANIMA_INSTALL_RUNNING) {
    $env:ANIMA_INSTALL_RUNNING = "1"
    $tempScript = Join-Path $env:TEMP "anima-install.ps1"
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    $wc = New-Object System.Net.WebClient
    $wc.Encoding = [System.Text.Encoding]::UTF8
    $wc.DownloadFile("https://raw.githubusercontent.com/longnull-ck/animaclaw/main/install.ps1", $tempScript)
    & powershell -ExecutionPolicy Bypass -File $tempScript
    $exitCode = $LASTEXITCODE
    Remove-Item $tempScript -ErrorAction SilentlyContinue
    Remove-Item Env:\ANIMA_INSTALL_RUNNING -ErrorAction SilentlyContinue
    exit $exitCode
}

$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "  Anima - AI Employee Installing..." -ForegroundColor Cyan
Write-Host ""

# -- Detect Python --
$Python = $null

if (Get-Command python3 -ErrorAction SilentlyContinue) {
    $Python = "python3"
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    $Python = "python"
}

if (-not $Python) {
    Write-Host "  [X] Python not found!" -ForegroundColor Red
    Write-Host ""
    Write-Host "  Please install Python 3.11+:"
    Write-Host "    https://www.python.org/downloads/"
    Write-Host "    (Check 'Add Python to PATH' during install)"
    Write-Host ""
    Read-Host "Press Enter to exit"
    exit 1
}

# Check version
$PyVersion = & $Python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
$PyMajor = & $Python -c "import sys; print(sys.version_info.major)"
$PyMinor = & $Python -c "import sys; print(sys.version_info.minor)"

if ([int]$PyMajor -lt 3 -or ([int]$PyMajor -eq 3 -and [int]$PyMinor -lt 11)) {
    Write-Host "  [X] Python version too old: $PyVersion (need 3.11+)" -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit 1
}

Write-Host "  [OK] Python $PyVersion ready" -ForegroundColor Green

# -- Clone repo (if not already in project dir) --
if (-not (Test-Path "pyproject.toml")) {
    Write-Host "  Downloading Anima..."
    if (Get-Command git -ErrorAction SilentlyContinue) {
        git clone https://github.com/longnull-ck/animaclaw.git anima-workspace
        Set-Location anima-workspace
    } else {
        Write-Host "  [X] Git not found! Install from: https://git-scm.com/download/win" -ForegroundColor Red
        Read-Host "Press Enter to exit"
        exit 1
    }
}

# -- Install dependencies --
Write-Host "  Installing dependencies..."
& $Python -m pip install -e ".[all]" --quiet 2>$null
if ($LASTEXITCODE -ne 0) {
    & $Python -m pip install -e ".[all]"
}

Write-Host "  [OK] Dependencies installed" -ForegroundColor Green

# -- Create .env file --
if (-not (Test-Path ".env")) {
    if (Test-Path ".env.example") {
        Copy-Item ".env.example" ".env"
        Write-Host "  [OK] .env file created" -ForegroundColor Green
    }
}

# -- Interactive init --
Write-Host ""
Write-Host "  --- Setup ---" -ForegroundColor Cyan
Write-Host ""
& $Python -m anima.cli init

Write-Host ""
Write-Host "  [OK] Setup complete, starting Anima..." -ForegroundColor Green
Write-Host ""

# -- Auto start --
& $Python run.py start
