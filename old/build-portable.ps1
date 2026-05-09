param(
    [string]$ProjectRoot = (Split-Path -Parent $MyInvocation.MyCommand.Path)
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$DesktopDir = Join-Path $ProjectRoot "desktop"
$BinariesDir = Join-Path $DesktopDir "src-tauri\binaries"
$DistDir = Join-Path $ProjectRoot "dist-portable"

function Step([string]$msg) {
    Write-Host ""
    Write-Host "==> $msg" -ForegroundColor Cyan
}

function Ok([string]$msg) {
    Write-Host "    OK: $msg" -ForegroundColor Green
}

function Fail([string]$msg) {
    Write-Host ""
    Write-Host "ERROR: $msg" -ForegroundColor Red
    exit 1
}

Step "Locating Python virtual environment"
$PythonCandidates = @(
    (Join-Path $ProjectRoot "venv\Scripts\python.exe"),
    (Join-Path $ProjectRoot ".venv\Scripts\python.exe")
)

$Python = $null
foreach ($p in $PythonCandidates) {
    if (Test-Path $p) { $Python = $p; break }
}
if (-not $Python) { Fail "venv not found. Run setup-desktop.ps1 first." }
Ok "Python: $Python"

Step "Checking PyInstaller"
& $Python -m pip install pyinstaller --quiet
if ($LASTEXITCODE -ne 0) { Fail "Could not install/verify PyInstaller" }
Ok "PyInstaller ready"

Step "Building agent_server.exe"
$AgentScript = Join-Path $ProjectRoot "agent_server.py"
if (-not (Test-Path $AgentScript)) { Fail "agent_server.py not found at $AgentScript" }

New-Item -ItemType Directory -Force -Path $BinariesDir | Out-Null

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

Push-Location $ProjectRoot
try {
    & $Python -m PyInstaller @PyiArgs
    if ($LASTEXITCODE -ne 0) { Fail "PyInstaller failed (exit $LASTEXITCODE)" }
} finally {
    Pop-Location
}

$AgentExe = Join-Path $BinariesDir "agent_server.exe"
if (-not (Test-Path $AgentExe)) { Fail "agent_server.exe not produced at $AgentExe" }
Ok "Built $AgentExe"

Step "Building desktop app (tauri)"
Push-Location $DesktopDir
try {
    npx tauri build
    if ($LASTEXITCODE -ne 0) { Fail "Tauri build failed (exit $LASTEXITCODE)" }
} finally {
    Pop-Location
}

Step "Collecting artifacts"
$TauriTarget = Join-Path $DesktopDir "src-tauri\target\release"
$AppExe = Join-Path $TauriTarget "UNLZ Agent.exe"
if (-not (Test-Path $AppExe)) {
    $AppExe = Join-Path $TauriTarget "unlz-agent.exe"
}
if (-not (Test-Path $AppExe)) { Fail "Could not find release exe in $TauriTarget" }

if (Test-Path $DistDir) { Remove-Item $DistDir -Recurse -Force }
New-Item -ItemType Directory -Force -Path $DistDir | Out-Null

Copy-Item $AppExe (Join-Path $DistDir "UNLZ Agent.exe")
Copy-Item $AgentExe (Join-Path $DistDir "agent_server.exe")

$EnvFile = Join-Path $ProjectRoot ".env"
if (Test-Path $EnvFile) {
    Copy-Item $EnvFile (Join-Path $DistDir ".env")
    Ok ".env copied"
} else {
    $EnvExample = Join-Path $ProjectRoot ".env.example"
    if (Test-Path $EnvExample) {
        Copy-Item $EnvExample (Join-Path $DistDir ".env")
        Ok ".env.example copied as .env"
    }
}

$WebViewDll = Join-Path $TauriTarget "WebView2Loader.dll"
if (Test-Path $WebViewDll) {
    Copy-Item $WebViewDll (Join-Path $DistDir "WebView2Loader.dll")
    Ok "WebView2Loader.dll copied"
}

Write-Host ""
Write-Host "Portable build ready:" -ForegroundColor Magenta
Write-Host "  $DistDir" -ForegroundColor White
Write-Host ""
