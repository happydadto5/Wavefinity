@echo off
setlocal
set "ROOT=%~dp0"
set "ZIP=%ROOT%wave.zip"

powershell -NoProfile -ExecutionPolicy Bypass -File "%ROOT%Make_Wave_Zip.ps1"
if errorlevel 1 (
  echo Failed to create wave.zip.
  exit /b 1
)

echo Created "%ZIP%"
