##############################################################################
#  build-portable.ps1
#  Builds a portable UNLZ Agent — double-click the .exe, no installer needed.
#
#  Output: dist-portable\
#            UNLZ Agent.exe        ← Tauri app
#            agent_server.exe      ← Python backend (PyInstaller)
#            WebView2Loader.dll    ← copied automatically by Tauri bundle
#            .env                  ← copied from project root
#
#  Requirements:
#    • Python venv at <project-root>/venv (created by setup-desktop.ps1)
#    • Rust + cargo-tauri  (cargo install tauri-cli --version "^2")
#    • PyInstaller          (pip install pyinstaller)
##############################################################################

param(
    [string]$ProjectRoot = (Split-Path -Parent $MyInvocation.MyCommand.Path)
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$DesktopDir  = Join-Path $ProjectRoot "desktop"
$BinariesDir = Join-Path $DesktopDir  "src-tauri\binaries"
$DistDir     = Join-Path $ProjectRoot "dist-portable"

# ── Helpers ───────────────────────────────────────────────────────────────────

function Step([string]$msg) {
    Write-Host "`n▶  $msg" -ForegroundColor Cyan
}

function Ok([string]$msg) {
    Write-Host "   ✓ $msg" -ForegroundColor Green
}

function Fail([string]$msg) {
    Write-Host "`n✗  $msg" -ForegroundColor Red
    exit 1
}

# ── Locate Python ──────────────────────────────────────────────────────────────

Step "Locating Python in venv"

$PythonPaths = @(
    (Join-Path $ProjectRoot "venv\Scripts\python.exe"),
    (Join-Path $ProjectRoot ".venv\Scripts\python.exe")
)

$Python = $null
foreach ($p in $PythonPaths) {
    if (Test-Path $p) { $Python = $p; break }
}

if (-not $Python) { Fail "venv not found. Run setup-desktop.ps1 first." }
Ok "Python: $Python"

# ── Check PyInstaller ────────────────────────────────────────────────────────

Step "Checking PyInstaller"
$pip = Join-Path (Split-Path $Python) "pip.exe"
$checkPyi = & $Python -c "import PyInstaller; print('ok')" 2>&1
if ($checkPyi -ne "ok") {
    Write-Host "   Installing PyInstaller…" -ForegroundColor Yellow
    & $pip install pyinstaller --quiet
}
Ok "PyInstaller ready"

# ── Build agent_server.exe ───────────────────────────────────────────────────

Step "Building agent_server.exe with PyInstaller"

$AgentScript = Join-Path $ProjectRoot "agent_server.py"
if (-not (Test-Path $AgentScript)) { Fail "agent_server.py not found at $AgentScript" }

# Collect hidden imports that PyInstaller might miss
$HiddenImports = @(
    "uvicorn.logging",
    "uvicorn.loops",
    "uvicorn.loops.auto",
    "uvicorn.protocols",
    "uvicorn.protocols.http",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.websockets",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan",
    "uvicorn.lifespan.on",
    "uvicorn.main",
    "fastapi",
    "pydantic",
    "openai",
    "langchain",
    "langchain_community",
    "langchain_chroma",
    "chromadb",
    "duckduckgo_search",
    "psutil",
    "dotenv"
)

$HiddenArgs = ($HiddenImports | ForEach-Object { "--hidden-import=$_" }) -join " "

$PyiArgs = @(
    $AgentScript,
    "--onefile",
    "--name", "agent_server",
    "--distpath", $BinariesDir,
    "--workpath", (Join-Path $ProjectRoot "build\_pyinstaller"),
    "--specpath", (Join-Path $ProjectRoot "build\_pyinstaller"),
    "--noconfirm",
    "--log-level", "WARN"
) + ($HiddenImports | ForEach-Object { "--hidden-import=$_" })

New-Item -ItemType Directory -Force -Path $BinariesDir | Out-Null

Push-Location $ProjectRoot
try {
    & $Python -m PyInstaller @PyiArgs
    if ($LASTEXITCODE -ne 0) { Fail "PyInstaller failed (exit $LASTEXITCODE)" }
} finally {
    Pop-Location
}

$AgentExe = Join-Path $BinariesDir "agent_server.exe"
if (-not (Test-Path $AgentExe)) { Fail "agent_server.exe not produced at $AgentExe" }
Ok "agent_server.exe built ($(([System.IO.FileInfo]$AgentExe).Length / 1MB | ForEach-Object { '{0:F1}' -f $_ }) MB)"

# ── Build Tauri app ──────────────────────────────────────────────────────────

Step "Building Tauri app (cargo tauri build)"

Push-Location $DesktopDir
try {
    npx tauri build
    if ($LASTEXITCODE -ne 0) { Fail "Tauri build failed (exit $LASTEXITCODE)" }
} finally {
    Pop-Location
}

# ── Locate built exe ─────────────────────────────────────────────────────────

Step "Locating built executable"

$TauriTarget = Join-Path $DesktopDir "src-tauri\target\release"
$AppExe      = Join-Path $TauriTarget "UNLZ Agent.exe"

if (-not (Test-Path $AppExe)) {
    # Some versions output without spaces
    $AppExe = Join-Path $TauriTarget "unlz-agent.exe"
    if (-not (Test-Path $AppExe)) {
        Fail "Could not find release exe in $TauriTarget"
    }
}
Ok "Found: $AppExe"

# ── Assemble portable folder ─────────────────────────────────────────────────

Step "Assembling dist-portable\"

if (Test-Path $DistDir) { Remove-Item $DistDir -Recurse -Force }
New-Item -ItemType Directory -Force -Path $DistDir | Out-Null

# App exe
Copy-Item $AppExe (Join-Path $DistDir "UNLZ Agent.exe")

# Sidecar
Copy-Item $AgentExe (Join-Path $DistDir "agent_server.exe")

# .env
$EnvFile = Join-Path $ProjectRoot ".env"
if (Test-Path $EnvFile) {
    Copy-Item $EnvFile (Join-Path $DistDir ".env")
    Ok ".env copied"
} else {
    $EnvExample = Join-Path $ProjectRoot ".env.example"
    if (Test-Path $EnvExample) {
        Copy-Item $EnvExample (Join-Path $DistDir ".env")
        Ok ".env.example copied as .env — edit before use"
    }
}

# WebView2 DLLs if present next to app
foreach ($dll in @("WebView2Loader.dll")) {
    $src = Join-Path $TauriTarget $dll
    if (Test-Path $src) {
        Copy-Item $src (Join-Path $DistDir $dll)
        Ok "$dll copied"
    }
}

# ── Summary ───────────────────────────────────────────────────────────────────

Write-Host ""
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Magenta
Write-Host "  Portable build ready: $DistDir" -ForegroundColor White
Write-Host "  Copy the folder anywhere and double-click:"         -ForegroundColor Gray
Write-Host "    'UNLZ Agent.exe'" -ForegroundColor Yellow
Write-Host "  Edit .env in the folder to configure the LLM."     -ForegroundColor Gray
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Magenta
Write-Host ""
