@echo off
setlocal EnableExtensions

set "ROOT=%~dp0"
cd /d "%ROOT%"

echo ==> Installing Python dependencies
where python >nul 2>nul
if errorlevel 1 (
  echo [ERROR] Python was not found in PATH. Install Python 3.10+ and run again.
  exit /b 1
)

if not exist "venv\Scripts\python.exe" (
  echo Creating virtual environment in .\venv ...
  python -m venv venv
  if errorlevel 1 exit /b 1
)

"venv\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 exit /b 1

"venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 exit /b 1

echo ==> Installing frontend dependencies
where npm >nul 2>nul
if errorlevel 1 (
  echo [ERROR] npm was not found in PATH. Install Node.js 20+ and run again.
  exit /b 1
)

pushd "frontend"
if errorlevel 1 (
  echo [ERROR] Could not enter .\frontend
  exit /b 1
)

if exist "package-lock.json" (
  call npm ci
) else (
  call npm install
)
set "NPM_EXIT=%ERRORLEVEL%"
popd

if not "%NPM_EXIT%"=="0" exit /b %NPM_EXIT%

echo.
echo Installation complete.
echo Run start.bat to start the app.
exit /b 0
