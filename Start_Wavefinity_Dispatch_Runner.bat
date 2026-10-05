@echo off
setlocal
rem Fix 119 Packet B: compatibility-named "ensure the NN Poller is running" shim.
rem Wavefinity dispatch now lives entirely in the NN desktop Poller; this file only
rem asks NN's launcher to make sure that Poller is up.  It contains no dispatch
rem logic, starts no Scheduled Task, never pauses, and is best-effort: Wavefinity
rem startup must never depend on it succeeding.  -EnsureRunning leaves a healthy
rem Poller completely alone (no stop, restart or takeover) and starts one only
rem when none is running.
rem
rem NN checkout: %WAVEFINITY_NN_DIR% if set, otherwise %USERPROFILE%\nn.
set "NN_DIR=%WAVEFINITY_NN_DIR%"
if not defined NN_DIR set "NN_DIR=%USERPROFILE%\nn"
set "NN_LAUNCHER=%NN_DIR%\start-poller-unified.ps1"
set "SHIM_LOG_DIR=%LOCALAPPDATA%\Wavefinity"
set "SHIM_LOG=%SHIM_LOG_DIR%\ensure-nn-poller.log"

if not exist "%NN_LAUNCHER%" (
    call :logfail "NN launcher not found: %NN_LAUNCHER%"
    exit /b 1
)

"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -NonInteractive -ExecutionPolicy Bypass -WindowStyle Hidden -File "%NN_LAUNCHER%" -NoPrompt -EnsureRunning >nul 2>&1
set "ENSURE_EXIT=%errorlevel%"
if not "%ENSURE_EXIT%"=="0" (
    call :logfail "NN launcher returned exit %ENSURE_EXIT%: %NN_LAUNCHER%"
    exit /b 1
)
exit /b 0

:logfail
if not exist "%SHIM_LOG_DIR%" mkdir "%SHIM_LOG_DIR%" >nul 2>&1
>>"%SHIM_LOG%" echo %DATE% %TIME% %~1
exit /b 0
