@echo off
setlocal EnableExtensions EnableDelayedExpansion

set "ROOT=%~dp0"
cd /d "%ROOT%"
set "N8N_PORT=%N8N_PORT%"
if "%N8N_PORT%"=="" set "N8N_PORT=5678"

if not exist "frontend\package.json" (
  echo [ERROR] frontend\package.json was not found.
  echo Run this script from the repository root.
  exit /b 1
)

where npm >nul 2>nul
if errorlevel 1 (
  echo [ERROR] npm was not found in PATH. Install Node.js and run again.
  exit /b 1
)

if not exist "frontend\node_modules" (
  echo [ERROR] frontend\node_modules was not found. Run install.bat first.
  exit /b 1
)

if /I not "%SKIP_N8N_AUTO_START%"=="1" (
  set "N8N_WAS_RUNNING=0"
  set "N8N_WORKFLOW_CHANGED="
  call :is_port_listening "%N8N_PORT%"
  if not errorlevel 1 set "N8N_WAS_RUNNING=1"

  call :ensure_default_webhook_url
  call :ensure_n8n_chat_workflow

  if "%N8N_WAS_RUNNING%"=="0" (
    echo [INFO] n8n is not running on port %N8N_PORT%. Attempting to start...
    call :start_n8n
    if errorlevel 1 (
      echo [WARNING] Could not auto-start n8n. Continue manually if needed.
    ) else (
      call :wait_for_port "%N8N_PORT%" "30"
      if errorlevel 1 (
        echo [WARNING] n8n did not open port %N8N_PORT% after 30s.
      ) else (
        echo [INFO] n8n is running on port %N8N_PORT%.
      )
    )
  ) else (
    echo [INFO] n8n already running on port %N8N_PORT%.
    if defined N8N_WORKFLOW_CHANGED (
      echo [WARNING] n8n workflow was updated while n8n is running.
      echo [WARNING] Restart n8n so webhook activation takes effect.
    )
  )
)

if exist "venv\Scripts\python.exe" (
  set "MCP_PYTHON=%ROOT%venv\Scripts\python.exe"
  echo Using MCP_PYTHON: !MCP_PYTHON!
) else if exist ".venv\Scripts\python.exe" (
  set "MCP_PYTHON=%ROOT%.venv\Scripts\python.exe"
  echo Using MCP_PYTHON: !MCP_PYTHON!
) else (
  echo [WARNING] venv Python not found. MCP will fall back to system Python.
  set "MCP_PYTHON=python"
)

set "MCP_PORT=8000"
if exist "%ROOT%.env" (
  for /f "usebackq tokens=1,* delims==" %%A in ("%ROOT%.env") do (
    if /I "%%A"=="MCP_PORT" if not "%%B"=="" set "MCP_PORT=%%B"
  )
)
if /I not "%SKIP_MCP_AUTO_START%"=="1" (
  call :ensure_mcp_running
)

call :cleanup_frontend_instances

pushd "frontend"
if errorlevel 1 (
  echo [ERROR] Could not enter .\frontend
  exit /b 1
)

if exist ".next\dev\lock" (
  del /f /q ".next\dev\lock" >nul 2>nul
  if exist ".next\dev\lock" (
    echo [WARNING] Could not remove frontend\.next\dev\lock
  ) else (
    echo [INFO] Removed stale frontend\.next\dev\lock
  )
)

call npm run dev
set "DEV_EXIT=%ERRORLEVEL%"
popd

exit /b %DEV_EXIT%

:ensure_mcp_running
set "MCP_SCRIPT=%ROOT%mcp_server.py"
if not exist "%MCP_SCRIPT%" (
  echo [WARNING] mcp_server.py was not found. Skipping MCP auto-start.
  exit /b 1
)

call :is_port_listening "%MCP_PORT%"
if not errorlevel 1 (
  echo [INFO] MCP already running on port %MCP_PORT%.
  exit /b 0
)

echo [INFO] MCP is not running on port %MCP_PORT%. Attempting to start...
cmd /c start "" /min "%MCP_PYTHON%" -u "%MCP_SCRIPT%"
call :wait_for_port "%MCP_PORT%" "20"
if errorlevel 1 (
  echo [WARNING] MCP did not open port %MCP_PORT% after 20s.
  exit /b 1
)

echo [INFO] MCP is running on port %MCP_PORT%.
exit /b 0

:cleanup_frontend_instances
set "FRONTEND_DIR=%ROOT%frontend"
powershell -NoProfile -Command ^
  "$frontend=(Resolve-Path '%FRONTEND_DIR%').Path;" ^
  "$procs=Get-CimInstance Win32_Process -Filter ""Name='node.exe'"" -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -and $_.CommandLine -like ""*next*dev*"" -and $_.CommandLine -like ""*$frontend*"" };" ^
  "if ($procs) { foreach ($p in $procs) { try { Stop-Process -Id $p.ProcessId -Force -ErrorAction Stop } catch {} }; Write-Output ('[INFO] Killed ' + $procs.Count + ' old Next.js process(es) from this repo.') }" 2>nul
exit /b 0

:is_port_listening
powershell -NoProfile -Command "$p=%~1; if (Get-NetTCPConnection -LocalPort $p -State Listen -ErrorAction SilentlyContinue) { exit 0 } else { exit 1 }" >nul 2>nul
exit /b %ERRORLEVEL%

:wait_for_port
set "_WAIT_PORT=%~1"
set "_WAIT_SECS=%~2"
for /L %%I in (1,1,%_WAIT_SECS%) do (
  call :is_port_listening "%_WAIT_PORT%"
  if not errorlevel 1 exit /b 0
  powershell -NoProfile -Command "Start-Sleep -Seconds 1" >nul
)
exit /b 1

:start_n8n
set "NODE_EXE="
set "NODE_DIR="
set "N8N_CMD="

for /f "delims=" %%F in ('where node 2^>nul') do (
  set "NODE_EXE=%%F"
  goto :got_node
)

:got_node
if defined NODE_EXE (
  for %%D in ("!NODE_EXE!") do set "NODE_DIR=%%~dpD"
  if exist "!NODE_DIR!n8n.cmd" (
    set "N8N_CMD=!NODE_DIR!n8n.cmd"
    for /f "delims=" %%V in ('"!N8N_CMD!" --version 2^>nul') do set "N8N_VER=%%V"
    echo [INFO] Starting n8n with !N8N_CMD! (v!N8N_VER!)
    cmd /c start "" /min "!N8N_CMD!" start
    exit /b 0
  )
)

where n8n.cmd >nul 2>nul
if not errorlevel 1 (
  echo [INFO] Starting n8n with n8n.cmd from PATH
  cmd /c start "" /min n8n.cmd start
  exit /b 0
)

where npx >nul 2>nul
if not errorlevel 1 (
  echo [INFO] Starting n8n with npx
  cmd /c start "" /min npx n8n start
  exit /b 0
)

echo [WARNING] n8n command was not found in PATH.
exit /b 1

:resolve_n8n_cli
if defined N8N_CLI_CMD exit /b 0

if defined N8N_CMD (
  if exist "!N8N_CMD!" (
    set "N8N_CLI_CMD=""!N8N_CMD!"""
    exit /b 0
  )
)

where n8n >nul 2>nul
if not errorlevel 1 (
  set "N8N_CLI_CMD=n8n"
  exit /b 0
)

where n8n.cmd >nul 2>nul
if not errorlevel 1 (
  set "N8N_CLI_CMD=n8n.cmd"
  exit /b 0
)

where npx >nul 2>nul
if not errorlevel 1 (
  set "N8N_CLI_CMD=npx n8n"
  exit /b 0
)

exit /b 1

:n8n_cli
if not defined N8N_CLI_CMD (
  call :resolve_n8n_cli
  if errorlevel 1 exit /b 1
)

call %N8N_CLI_CMD% %*
exit /b %ERRORLEVEL%

:find_n8n_workflow_id
set "FOUND_WORKFLOW_ID="
set "WF_LOOKUP_NAME=%~1"
if "%WF_LOOKUP_NAME%"=="" exit /b 1

if not defined N8N_CLI_CMD (
  call :resolve_n8n_cli
  if errorlevel 1 exit /b 1
)

for /f "tokens=1,* delims=|" %%A in ('call %N8N_CLI_CMD% list:workflow 2^>nul') do (
  if /I "%%B"=="!WF_LOOKUP_NAME!" (
    set "FOUND_WORKFLOW_ID=%%A"
  )
)

if defined FOUND_WORKFLOW_ID (
  exit /b 0
)

exit /b 1

:is_n8n_workflow_active
set "WORKFLOW_IS_ACTIVE="
set "WF_ACTIVE_ID=%~1"
if "%WF_ACTIVE_ID%"=="" exit /b 1

if not defined N8N_CLI_CMD (
  call :resolve_n8n_cli
  if errorlevel 1 exit /b 1
)

for /f "tokens=1,* delims=|" %%A in ('call %N8N_CLI_CMD% list:workflow --active=true 2^>nul') do (
  if /I "%%A"=="!WF_ACTIVE_ID!" (
    set "WORKFLOW_IS_ACTIVE=1"
  )
)

if defined WORKFLOW_IS_ACTIVE exit /b 0
exit /b 1

:ensure_default_webhook_url
powershell -NoProfile -Command ^
  "$envPath = Join-Path '%ROOT%' '.env';" ^
  "$defaultUrl = 'http://127.0.0.1:%N8N_PORT%/webhook/chat';" ^
  "if (-not (Test-Path $envPath)) { Set-Content -Path $envPath -Value ('N8N_WEBHOOK_URL=' + $defaultUrl); exit 0 }" ^
  "$lines = Get-Content $envPath;" ^
  "$found = $false;" ^
  "for ($i = 0; $i -lt $lines.Count; $i++) {" ^
  "  if ($lines[$i] -match '^N8N_WEBHOOK_URL=') {" ^
  "    $found = $true;" ^
  "    if ((($lines[$i] -replace '^N8N_WEBHOOK_URL=', '')).Trim() -eq '') { $lines[$i] = 'N8N_WEBHOOK_URL=' + $defaultUrl }" ^
  "    break;" ^
  "  }" ^
  "}" ^
  "if (-not $found) { $lines += ('N8N_WEBHOOK_URL=' + $defaultUrl) }" ^
  "Set-Content -Path $envPath -Value $lines" >nul 2>nul

if errorlevel 1 (
  echo [WARNING] Could not ensure N8N_WEBHOOK_URL in .env
) else (
  echo [INFO] N8N_WEBHOOK_URL checked in .env
)
exit /b 0

:ensure_n8n_chat_workflow
set "WF_FILE=%ROOT%n8n_workflow.json"
set "WF_NAME=UNLZ Agent (Multi-Modal)"

if not exist "%WF_FILE%" (
  echo [WARNING] %WF_FILE% was not found. Skipping n8n workflow auto-import.
  exit /b 1
)

call :find_n8n_workflow_id "%WF_NAME%"
if not errorlevel 1 (
  echo [INFO] n8n workflow "!WF_NAME!" already exists ^(ID: !FOUND_WORKFLOW_ID!^).
) else (
  echo [INFO] n8n webhook workflow missing. Importing "%WF_FILE%"...
  call :n8n_cli import:workflow --input="%WF_FILE%" >nul 2>nul
  if errorlevel 1 (
    echo [WARNING] Could not import n8n workflow automatically.
    exit /b 1
  )
  call :find_n8n_workflow_id "%WF_NAME%"
  if errorlevel 1 (
    echo [WARNING] Workflow import finished but could not find "!WF_NAME!".
    exit /b 1
  )
  echo [INFO] n8n workflow imported ^(ID: !FOUND_WORKFLOW_ID!^).
)

if defined FOUND_WORKFLOW_ID (
  call :is_n8n_workflow_active "!FOUND_WORKFLOW_ID!"
  if errorlevel 1 (
    call :n8n_cli update:workflow --id=!FOUND_WORKFLOW_ID! --active=true >nul 2>nul
    if errorlevel 1 (
      echo [WARNING] Could not auto-activate n8n workflow !FOUND_WORKFLOW_ID!.
    ) else (
      set "N8N_WORKFLOW_CHANGED=1"
      echo [INFO] n8n workflow !FOUND_WORKFLOW_ID! was activated.
    )
  ) else (
    echo [INFO] n8n workflow !FOUND_WORKFLOW_ID! is already active.
  )
)

exit /b 0
