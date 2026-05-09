#!/usr/bin/env pwsh
# setup-desktop.ps1 — First-time setup for UNLZ Agent desktop app
# Run from the project root: .\setup-desktop.ps1

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path

Write-Host ""
Write-Host "  UNLZ Agent — Desktop Setup" -ForegroundColor Cyan
Write-Host "  ──────────────────────────" -ForegroundColor DarkGray
Write-Host ""

# ── 1. Check Rust ─────────────────────────────────────────────────────────────
Write-Host "[1/5] Checking Rust..." -ForegroundColor Yellow
$cargoPath = "$env:USERPROFILE\.cargo\bin\cargo.exe"

if (Test-Path $cargoPath) {
    & $cargoPath --version
    $env:PATH = "$env:USERPROFILE\.cargo\bin;$env:PATH"
    Write-Host "  ✓ Rust found" -ForegroundColor Green
} elseif (Get-Command cargo -ErrorAction SilentlyContinue) {
    cargo --version
    Write-Host "  ✓ Rust found in PATH" -ForegroundColor Green
} else {
    Write-Host "  Rust not found. Installing via winget..." -ForegroundColor Yellow
    winget install --id Rustlang.Rustup --silent --accept-package-agreements --accept-source-agreements
    # Refresh PATH
    $env:PATH = "$env:USERPROFILE\.cargo\bin;$env:PATH"
    # Run rustup to install default toolchain
    if (Test-Path "$env:USERPROFILE\.cargo\bin\rustup.exe") {
        & "$env:USERPROFILE\.cargo\bin\rustup.exe" toolchain install stable
    }
    Write-Host "  ✓ Rust installed" -ForegroundColor Green
}

# ── 2. Python venv ────────────────────────────────────────────────────────────
Write-Host "[2/5] Setting up Python virtualenv..." -ForegroundColor Yellow
$venvPath = Join-Path $Root "venv"

if (-not (Test-Path $venvPath)) {
    python -m venv $venvPath
    Write-Host "  ✓ venv created" -ForegroundColor Green
} else {
    Write-Host "  ✓ venv already exists" -ForegroundColor Green
}

$pip = Join-Path $venvPath "Scripts\pip.exe"
& $pip install --quiet --upgrade pip
& $pip install --quiet -r (Join-Path $Root "requirements.txt")
Write-Host "  ✓ Python dependencies installed" -ForegroundColor Green

# ── 3. Node.js deps for desktop ───────────────────────────────────────────────
Write-Host "[3/5] Installing Node.js dependencies..." -ForegroundColor Yellow
Push-Location (Join-Path $Root "desktop")
npm install --silent
Pop-Location
Write-Host "  ✓ Node.js dependencies installed" -ForegroundColor Green

# ── 4. Tauri icons (generate placeholder if missing) ──────────────────────────
Write-Host "[4/5] Checking Tauri icons..." -ForegroundColor Yellow
$iconsDir = Join-Path $Root "desktop\src-tauri\icons"
$requiredIcon = Join-Path $iconsDir "icon.ico"

if (-not (Test-Path $requiredIcon)) {
    Write-Host "  Icons missing — generating placeholders..." -ForegroundColor Yellow
    # Use a bundled PowerShell icon generator (creates simple colored icons)
    $iconScript = @"
Add-Type -AssemblyName System.Drawing

function New-PngIcon([string]\$path, [int]\$size) {
    \$bmp = New-Object System.Drawing.Bitmap(\$size, \$size)
    \$g = [System.Drawing.Graphics]::FromImage(\$bmp)
    \$g.Clear([System.Drawing.Color]::FromArgb(11,11,18))
    \$brush = New-Object System.Drawing.SolidBrush([System.Drawing.Color]::FromArgb(124,106,245))
    \$g.FillEllipse(\$brush, \$size*0.1, \$size*0.1, \$size*0.8, \$size*0.8)
    \$font = New-Object System.Drawing.Font("Arial", \$size*0.35, [System.Drawing.FontStyle]::Bold)
    \$textBrush = New-Object System.Drawing.SolidBrush([System.Drawing.Color]::White)
    \$sf = New-Object System.Drawing.StringFormat
    \$sf.Alignment = [System.Drawing.StringAlignment]::Center
    \$sf.LineAlignment = [System.Drawing.StringAlignment]::Center
    \$g.DrawString("U", \$font, \$textBrush, [System.Drawing.RectangleF]::new(0,0,\$size,\$size), \$sf)
    \$bmp.Save(\$path, [System.Drawing.Imaging.ImageFormat]::Png)
    \$g.Dispose(); \$bmp.Dispose()
}

\$dir = '$iconsDir'
New-PngIcon (Join-Path \$dir "32x32.png") 32
New-PngIcon (Join-Path \$dir "128x128.png") 128
New-PngIcon (Join-Path \$dir "128x128@2x.png") 256

# Create a minimal .ico (copy 32x32.png, rename)
Copy-Item (Join-Path \$dir "32x32.png") (Join-Path \$dir "icon.ico") -Force

# Placeholder for macOS (Tauri will skip on Windows)
Copy-Item (Join-Path \$dir "128x128.png") (Join-Path \$dir "icon.icns") -Force
"@
    Invoke-Expression $iconScript
    Write-Host "  ✓ Placeholder icons created" -ForegroundColor Green
} else {
    Write-Host "  ✓ Icons present" -ForegroundColor Green
}

# ── 5. .env from example ──────────────────────────────────────────────────────
Write-Host "[5/5] Checking .env..." -ForegroundColor Yellow
$envFile = Join-Path $Root ".env"
$envExample = Join-Path $Root ".env.example"

if (-not (Test-Path $envFile) -and (Test-Path $envExample)) {
    Copy-Item $envExample $envFile
    Write-Host "  ✓ .env created from .env.example — edit it before running!" -ForegroundColor Yellow
} elseif (Test-Path $envFile) {
    Write-Host "  ✓ .env already exists" -ForegroundColor Green
} else {
    Write-Host "  ⚠ No .env.example found — create .env manually" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "  ✓ Setup complete!" -ForegroundColor Green
Write-Host ""
Write-Host "  Next steps:" -ForegroundColor Cyan
Write-Host "    1. Edit .env with your model paths"
Write-Host "    2. Run:  .\start-desktop.ps1"
Write-Host "       OR:   cd desktop && npx tauri dev"
Write-Host ""
