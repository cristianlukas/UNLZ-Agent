@echo off
setlocal EnableExtensions

set "ROOT=%~dp0"
cd /d "%ROOT%"
set "DO_CLEAN=0"

if /I "%~1"=="--clean" set "DO_CLEAN=1"
if /I "%~1"=="-c" set "DO_CLEAN=1"

if not exist "%ROOT%start-desktop.ps1" (
  echo [ERROR] No se encontro start-desktop.ps1 en:
  echo         %ROOT%
  exit /b 1
)

where powershell >nul 2>nul
if errorlevel 1 (
  echo [ERROR] PowerShell no esta disponible en PATH.
  exit /b 1
)

if "%DO_CLEAN%"=="1" (
  echo [INFO] Limpieza previa forzada habilitada...
  powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "$ErrorActionPreference='SilentlyContinue';" ^
    "$ports=@(1420,7719);" ^
    "foreach($p in $ports){Get-NetTCPConnection -State Listen | Where-Object {$_.LocalPort -eq $p} | Select-Object -ExpandProperty OwningProcess -Unique | ForEach-Object { try { Stop-Process -Id $_ -Force } catch {} }};" ^
    "foreach($n in @('unlz-agent','cargo','node','python','python3')){Get-Process -Name $n | ForEach-Object { try { Stop-Process -Id $_.Id -Force } catch {} }};" ^
    "$lock=Join-Path '%ROOT%' 'desktop\\src-tauri\\target\\release\\.cargo-lock'; if(Test-Path $lock){Remove-Item -Force $lock};" ^
    "Write-Output '[INFO] Limpieza previa completada.'"
)

echo [INFO] Iniciando UNLZ Agent GUI en modo desarrollo ^(sin instalar^)...
echo [INFO] Proyecto: %ROOT%
echo.

powershell -NoProfile -ExecutionPolicy Bypass -File "%ROOT%start-desktop.ps1"
set "EXIT_CODE=%ERRORLEVEL%"

if not "%EXIT_CODE%"=="0" (
  echo.
  echo [ERROR] start-desktop.ps1 finalizo con codigo %EXIT_CODE%.
)

exit /b %EXIT_CODE%
