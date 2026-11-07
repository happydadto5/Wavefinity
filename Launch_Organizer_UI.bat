@echo off
setlocal
set "PYTHONPATH="
set "WF_HOME=%LOCALAPPDATA%\Wavefinity"

rem Story 2647: stable launcher entry. activate_wavefinity_launcher.ps1 installs
rem this file, wavefinity_freshness.py and launcher.json together under
rem %LOCALAPPDATA%\Wavefinity\Launcher\versions\[id], independent of every
rem working checkout. A copy with launcher.json beside it is the real launcher.
rem Any other copy - a Wavefinity checkout, or the old shortcut chain - is only a
rem shim: it hands over to the installed current version, or stops. It never
rem starts a server from the checkout it sits in, so a stale or wrong-branch
rem checkout can never be what runs.
if exist "%~dp0launcher.json" goto :launch

if not exist "%WF_HOME%\Launcher\current.txt" goto :notinstalled
findstr /r /x /c:"[0-9A-Za-z][0-9A-Za-z._-]*" "%WF_HOME%\Launcher\current.txt" >nul 2>&1
if errorlevel 1 goto :notinstalled
set "WF_CURRENT="
set /p WF_CURRENT=<"%WF_HOME%\Launcher\current.txt"
if not exist "%WF_HOME%\Launcher\versions\%WF_CURRENT%\launcher.json" goto :notinstalled
call "%WF_HOME%\Launcher\versions\%WF_CURRENT%\Launch_Organizer_UI.bat" %*
exit /b %errorlevel%

:notinstalled
call :fail "Wavefinity's stable launcher is not installed, so nothing was started. Run activate_wavefinity_launcher.ps1 from the approved Wavefinity checkout to install it."
exit /b 2

:launch
set "WF_PY=%WF_HOME%\Env\Scripts\python.exe"
if not exist "%WF_PY%" goto :noenv

rem The freshness module owns every decision: remote check, runtime checkout,
rem server hand-off, health verification and the browser. It prints the outcome
rem - READY, RUNNING UNVERIFIED or STOPPED with the action to take - and, when
rem Launch_Organizer_UI.vbs started this run, writes it to the status file the
rem VBS shows. --check reports without changing anything.
if /i "%~1"=="--check" (
    "%WF_PY%" "%~dp0wavefinity_freshness.py" --check
) else (
    "%WF_PY%" "%~dp0wavefinity_freshness.py" --launch
)
set "WF_EXIT=%errorlevel%"
if "%WF_EXIT%"=="0" exit /b 0
if defined WAVEFINITY_STATUS_FILE exit /b %WF_EXIT%
echo.
echo Wavefinity did not start. Follow the instructions above, then run the launcher again.
if /i not "%~1"=="--check" pause
exit /b %WF_EXIT%

:noenv
call :fail "Wavefinity's Python environment is missing, so nothing was started. Run activate_wavefinity_launcher.ps1 from the approved Wavefinity checkout to rebuild it."
exit /b 2

rem The message argument must not contain parentheses, ampersands or percent signs.
:fail
echo.
echo %~1
if not defined WAVEFINITY_STATUS_FILE goto :failpause
> "%WAVEFINITY_STATUS_FILE%" echo STOPPED
>> "%WAVEFINITY_STATUS_FILE%" echo %~1
exit /b 0
:failpause
pause
exit /b 0
