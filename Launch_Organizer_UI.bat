@echo off
setlocal
cd /d "%~dp0"
set "PYTHONPATH="
set "ORGANIZER_ENV=%~dp0.venv"
set "ORGANIZER_PY=%ORGANIZER_ENV%\Scripts\python.exe"
set "ORGANIZER_PYW=%ORGANIZER_ENV%\Scripts\pythonw.exe"

if not exist "%ORGANIZER_PY%" (
    echo Preparing the organizer app for first use...
    where python >nul 2>&1
    if not errorlevel 1 (
        python -m venv "%ORGANIZER_ENV%"
    ) else (
        where py >nul 2>&1
        if errorlevel 1 (
            echo Python 3 was not found. Install Python from python.org and run this launcher again.
            goto :failed
        )
        py -3 -m venv "%ORGANIZER_ENV%"
    )
    if errorlevel 1 goto :failed
)

"%ORGANIZER_PY%" -c "import cv2, lib3mf, lxml, manifold3d, mapbox_earcut, matplotlib, networkx, numpy, shapely, trimesh" >nul 2>&1
if errorlevel 1 (
    echo Installing the organizer geometry components. This is only needed on first launch...
    "%ORGANIZER_PY%" -m pip install --disable-pip-version-check opencv-python-headless==5.0.0.93 lib3mf==2.5.0 lxml==6.1.2 manifold3d==3.5.2 mapbox-earcut==2.0.0 matplotlib==3.11.1 networkx==3.6.1 numpy==2.5.2 shapely==2.1.2 trimesh==5.0.0
    if errorlevel 1 goto :failed
)

if /i "%~1"=="--check" (
    "%ORGANIZER_PY%" wavefinity_freshness.py --check
    if errorlevel 1 exit /b 1
    exit /b 0
)

rem Fix 096 A6: source freshness gate. A clean main branch that is merely
rem behind origin/main is fast-forwarded; dirty, ahead, diverged, detached,
rem or wrong-branch states either proceed with a notice or stop here with
rem plain instructions. The gate never resets, cleans, stashes, rebases, or
rem force-updates.
"%ORGANIZER_PY%" wavefinity_freshness.py --ensure-current
if errorlevel 2 goto :updateblocked
if errorlevel 1 goto :failed

rem Run the long-lived local server without attaching it to this command
rem window.  A later launch may replace it without leaving a paused window.
start "" "%ORGANIZER_PYW%" wavefinity_web.py
if errorlevel 1 goto :failed
exit /b 0

:updateblocked
echo.
echo Wavefinity did not start. Follow the instructions above, then run the launcher again.
if /i not "%~1"=="--check" pause
exit /b 1

:failed
echo.
echo The organizer app could not be prepared. Review the message above and try again.
if /i not "%~1"=="--check" pause
exit /b 1
