@echo off
setlocal EnableExtensions EnableDelayedExpansion

set "ROOT=%~dp0"
cd /d "%ROOT%"

echo ==> Building single EXE installer (NSIS) with offline WebView2

set "PYTHON=%ROOT%venv\Scripts\python.exe"
if not exist "%PYTHON%" set "PYTHON=%ROOT%.venv\Scripts\python.exe"
if not exist "%PYTHON%" (
  echo [ERROR] Python virtualenv not found. Run setup-desktop.ps1 first.
  exit /b 1
)

set "DESKTOP=%ROOT%desktop"
set "BIN_DIR=%DESKTOP%\src-tauri\binaries"
set "LLAMA_BIN_DIR=%BIN_DIR%\llama.cpp"
set "OUT_DIR=%ROOT%dist-single-exe"
set "ROOT_SETUP=%ROOT%UNLZ-Agent-Setup.exe"
set "AGENT_SCRIPT=%ROOT%agent_server.py"
set "AGENT_EXE=%BIN_DIR%\agent_server.exe"
set "MCP_SCRIPT=%ROOT%mcp_server.py"
set "MCP_EXE=%BIN_DIR%\mcp_server.exe"

if not exist "%AGENT_SCRIPT%" (
  echo [ERROR] agent_server.py not found.
  exit /b 1
)
if not exist "%MCP_SCRIPT%" (
  echo [ERROR] mcp_server.py not found.
  exit /b 1
)

echo ==> Ensuring PyInstaller
"%PYTHON%" -m pip install pyinstaller --quiet
if errorlevel 1 (
  echo [ERROR] Could not install/verify PyInstaller.
  exit /b 1
)

if not exist "%BIN_DIR%" mkdir "%BIN_DIR%"

set "LLAMA_SOURCE=%ROOT%tools\llama.cpp\b8902"
if defined UNLZ_LLAMA_BUNDLE_SOURCE set "LLAMA_SOURCE=%UNLZ_LLAMA_BUNDLE_SOURCE%"
if not exist "%LLAMA_SOURCE%\llama-server.exe" (
  echo [ERROR] llama.cpp source invalid: "%LLAMA_SOURCE%"
  echo         Set UNLZ_LLAMA_BUNDLE_SOURCE to a folder that contains llama-server.exe
  exit /b 1
)

echo ==> Syncing bundled llama.cpp runtime
if exist "%LLAMA_BIN_DIR%" rmdir /s /q "%LLAMA_BIN_DIR%"
mkdir "%LLAMA_BIN_DIR%"
robocopy "%LLAMA_SOURCE%" "%LLAMA_BIN_DIR%" /E /NFL /NDL /NJH /NJS /NC /NS >nul
if errorlevel 8 (
  echo [ERROR] Failed to copy llama.cpp runtime.
  exit /b 1
)

echo ==> Building backend sidecar (agent_server.exe)
"%PYTHON%" -m PyInstaller "%AGENT_SCRIPT%" --onefile --name agent_server --distpath "%BIN_DIR%" --workpath "%ROOT%build\_pyinstaller" --specpath "%ROOT%build\_pyinstaller" --noconfirm --log-level WARN
if errorlevel 1 (
  echo [ERROR] PyInstaller failed.
  exit /b 1
)

if not exist "%AGENT_EXE%" (
  echo [ERROR] Sidecar not produced at "%AGENT_EXE%".
  exit /b 1
)

echo ==> Building MCP sidecar (mcp_server.exe)
"%PYTHON%" -m PyInstaller "%MCP_SCRIPT%" --onefile --name mcp_server --distpath "%BIN_DIR%" --workpath "%ROOT%build\_pyinstaller" --specpath "%ROOT%build\_pyinstaller" --noconfirm --log-level WARN
if errorlevel 1 (
  echo [ERROR] PyInstaller failed for mcp_server.
  exit /b 1
)

if not exist "%MCP_EXE%" (
  echo [ERROR] Sidecar not produced at "%MCP_EXE%".
  exit /b 1
)

pushd "%DESKTOP%"
echo ==> Building Tauri NSIS installer
call npx tauri build --bundles nsis
if errorlevel 1 (
  popd
  echo [ERROR] Tauri NSIS build failed.
  exit /b 1
)
popd

for /f "delims=" %%F in ('dir /b /s "%DESKTOP%\src-tauri\target\release\bundle\nsis\*.exe" 2^>nul') do (
  set "INSTALLER=%%F"
  goto :found
)

echo [ERROR] NSIS installer .exe not found.
exit /b 1

:found
if exist "%OUT_DIR%" rmdir /s /q "%OUT_DIR%"
mkdir "%OUT_DIR%"
copy /y "!INSTALLER!" "%OUT_DIR%\UNLZ-Agent-Setup.exe" >nul
copy /y "!INSTALLER!" "%ROOT_SETUP%" >nul

echo.
echo Build complete.
echo Installer copies:
echo   %OUT_DIR%\UNLZ-Agent-Setup.exe
echo   %ROOT_SETUP%
echo.
echo Users only need this one EXE installer.
exit /b 0
