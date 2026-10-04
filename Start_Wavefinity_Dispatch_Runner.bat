@echo off
setlocal
set "TASK_NAME=Wavefinity Dispatch Runner"

schtasks /query /tn "%TASK_NAME%" >nul 2>&1
if errorlevel 1 goto missing

schtasks /run /tn "%TASK_NAME%" >nul 2>&1
if errorlevel 1 goto failed

echo Wavefinity dispatch runner is starting or already running.
echo You can minimize its window, but leave it open to receive jobs.
timeout /t 4 /nobreak >nul
exit /b 0

:missing
echo The Wavefinity Dispatch Runner task is not installed on this PC.
echo Ask a local Codex chat to repair the dispatcher setup.
pause
exit /b 1

:failed
echo Windows could not start the Wavefinity Dispatch Runner task.
echo Check Task Scheduler or ask a local Codex chat to inspect it.
pause
exit /b 1
