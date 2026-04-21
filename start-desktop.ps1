#!/usr/bin/env pwsh
# start-desktop.ps1 — Launch UNLZ Agent desktop app (dev mode)
# Run from project root: .\start-desktop.ps1

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path

# ── Rust in PATH ──────────────────────────────────────────────────────────────
$rustBin = "$env:USERPROFILE\.cargo\bin"
if (Test-Path $rustBin) { $env:PATH = "$rustBin;$env:PATH" }

# ── Python venv (create + install if missing) ─────────────────────────────────
$venvPython = Join-Path $Root "venv\Scripts\python.exe"
$venvPip    = Join-Path $Root "venv\Scripts\pip.exe"

if (-not (Test-Path $venvPython)) {
    Write-Host "venv not found — creating..." -ForegroundColor Yellow

    # Find a usable python3
    $sysPython = $null
    foreach ($candidate in @("python", "python3", "py")) {
        try {
            $ver = & $candidate --version 2>&1
            if ($ver -match "Python 3") { $sysPython = $candidate; break }
        } catch { }
    }
    if (-not $sysPython) {
        Write-Host "ERROR: Python 3 not found in PATH. Install it first." -ForegroundColor Red
        exit 1
    }

    & $sysPython -m venv (Join-Path $Root "venv")
    if ($LASTEXITCODE -ne 0) {
        Write-Host "ERROR: venv creation failed." -ForegroundColor Red
        exit 1
    }
    Write-Host "venv created." -ForegroundColor Green
}

$hasFastApi = Test-Path (Join-Path $Root "venv\Lib\site-packages\fastapi")
$hasGoogleSearch = Test-Path (Join-Path $Root "venv\Lib\site-packages\googlesearch")
$hasDdgs = Test-Path (Join-Path $Root "venv\Lib\site-packages\ddgs")
if (-not $hasFastApi -or -not $hasGoogleSearch -or -not $hasDdgs) {
    Write-Host "Installing Python dependencies..." -ForegroundColor Yellow
    & $venvPip install -r (Join-Path $Root "requirements.txt") --quiet
    if ($LASTEXITCODE -ne 0) {
        Write-Host "ERROR: pip install failed." -ForegroundColor Red
        exit 1
    }
    Write-Host "Dependencies installed." -ForegroundColor Green
}

# ── .env (copy from example if missing) ──────────────────────────────────────
$envFile    = Join-Path $Root ".env"
$envExample = Join-Path $Root ".env.example"
if (-not (Test-Path $envFile) -and (Test-Path $envExample)) {
    Copy-Item $envExample $envFile
    Write-Host ".env created from .env.example — edit it to configure the model." -ForegroundColor Yellow
}

# ── npm install (if node_modules missing) ────────────────────────────────────
$nodeModules = Join-Path $Root "desktop\node_modules"
if (-not (Test-Path $nodeModules)) {
    Write-Host "Installing npm dependencies..." -ForegroundColor Yellow
    Push-Location (Join-Path $Root "desktop")
    npm install --silent
    if ($LASTEXITCODE -ne 0) {
        Write-Host "ERROR: npm install failed." -ForegroundColor Red
        Pop-Location; exit 1
    }
    Pop-Location
    Write-Host "npm dependencies installed." -ForegroundColor Green
}

# ── Export env vars for Rust ──────────────────────────────────────────────────
$env:UNLZ_PROJECT_ROOT = $Root
$env:UNLZ_PYTHON       = $venvPython

# ── Free dev ports (stale Vite / stale agent) ────────────────────────────────
foreach ($port in @(1420, 7719)) {
    try {
        $listeners = Get-NetTCPConnection -State Listen -ErrorAction Stop |
            Where-Object { $_.LocalPort -eq $port } |
            Select-Object -ExpandProperty OwningProcess -Unique

        foreach ($procId in $listeners) {
            if (-not $procId) { continue }
            try {
                $proc = Get-Process -Id $procId -ErrorAction Stop
                Write-Host ("Port {0} in use by {1} (PID {2}) — stopping..." -f $port, $proc.ProcessName, $procId) -ForegroundColor Yellow
                Stop-Process -Id $procId -Force -ErrorAction Stop
            } catch {
                Write-Host ("Warning: could not stop PID {0} on port {1}" -f $procId, $port) -ForegroundColor DarkYellow
            }
        }
    } catch {
        # Ignore if TCP table not available or no listeners found.
    }
}

# ── Stop stale Tauri/Cargo processes that lock target binaries ───────────────
foreach ($procName in @("unlz-agent", "cargo")) {
    $stale = Get-Process -Name $procName -ErrorAction SilentlyContinue
    foreach ($p in $stale) {
        try {
            Write-Host ("Stopping stale process {0} (PID {1})..." -f $p.ProcessName, $p.Id) -ForegroundColor Yellow
            Stop-Process -Id $p.Id -Force -ErrorAction Stop
        } catch {
            Write-Host ("Warning: could not stop {0} (PID {1})" -f $p.ProcessName, $p.Id) -ForegroundColor DarkYellow
        }
    }
}

# ── Launch ────────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "Starting UNLZ Agent desktop..." -ForegroundColor Cyan
Write-Host "  Project root : $Root"      -ForegroundColor DarkGray
Write-Host "  Python       : $venvPython" -ForegroundColor DarkGray
Write-Host ""

Set-Location (Join-Path $Root "desktop")
npx tauri dev
