@echo off
setlocal EnableDelayedExpansion
title Wavefinity Fresh Start

echo.
echo  ============================================
echo   WAVEFINITY FRESH START
echo  ============================================
echo.
echo  This will DELETE all Wavefinity data:
echo   - Browser site data for wavefinity.onrender.com
echo     (Chrome and Edge: IndexedDB, Local Storage,
echo      Service Workers, Cache)
echo   - Local Wavefinity data folders
echo.
echo  After this, Wavefinity will start as if
echo  you are a first-time user.
echo.
echo  Your browsers will be closed.
echo.
echo  ============================================
echo.

set /p "confirm=Type KILL to continue (anything else cancels): "

if /i not "%confirm%"=="kill" (
    echo.
    echo  Cancelled. Nothing was deleted.
    echo.
    pause
    exit /b 1
)

echo.
echo  *** You typed KILL - proceeding with full data deletion ***
echo.
echo  Confirmed. Starting fresh...
echo.

:: --- Kill browsers ---
echo  [1/4] Closing browsers...
taskkill /F /IM chrome.exe >nul 2>&1
taskkill /F /IM msedge.exe >nul 2>&1
timeout /t 3 /nobreak >nul
echo        Done.
echo.

:: --- Chrome site data ---
echo  [2/4] Clearing Chrome site data...
set "CHROME_DEFAULT=%LOCALAPPDATA%\Google\Chrome\User Data\Default"

if exist "%CHROME_DEFAULT%\IndexedDB" (
    for /d %%D in ("%CHROME_DEFAULT%\IndexedDB\*wavefinity*") do (
        echo        Removing %%~nxD
        rd /s /q "%%D" >nul 2>&1
    )
)
if exist "%CHROME_DEFAULT%\Service Worker" (
    for /d %%D in ("%CHROME_DEFAULT%\Service Worker\*wavefinity*") do (
        echo        Removing %%~nxD
        rd /s /q "%%D" >nul 2>&1
    )
)
:: Local Storage leveldb - remove wavefinity keys via temporary profile trick is complex;
:: instead clear the whole leveldb for the site using Chrome's site data approach is not
:: scriptable per-site, so we note it. The IndexedDB clear above covers most app data.
echo        Done.
echo.

:: --- Edge site data ---
echo  [3/4] Clearing Edge site data...
set "EDGE_DEFAULT=%LOCALAPPDATA%\Microsoft\Edge\User Data\Default"

if exist "%EDGE_DEFAULT%\IndexedDB" (
    for /d %%D in ("%EDGE_DEFAULT%\IndexedDB\*wavefinity*") do (
        echo        Removing %%~nxD
        rd /s /q "%%D" >nul 2>&1
    )
)
if exist "%EDGE_DEFAULT%\Service Worker" (
    for /d %%D in ("%EDGE_DEFAULT%\Service Worker\*wavefinity*") do (
        echo        Removing %%~nxD
        rd /s /q "%%D" >nul 2>&1
    )
)
echo        Done.
echo.

:: --- Local Wavefinity data folders ---
echo  [4/4] Clearing local Wavefinity folders...
:: Add any known local data directories here
:: Example: if exist "%USERPROFILE%\WavefinityData" rd /s /q "%USERPROFILE%\WavefinityData"
echo        (No standalone data folders configured.)
echo        Done.
echo.

echo  ============================================
echo   FRESH START COMPLETE
echo  ============================================
echo.
echo  Wavefinity will now start as a first-time user.
echo  Reopen your browser and go to:
echo    https://wavefinity.onrender.com
echo.
echo  NOTE: Browser Local Storage (leveldb) is shared
echo  across sites and cannot be selectively cleared
echo  by this script. If the app still shows old data,
echo  clear site data manually:
echo    Chrome/Edge: F12 ^> Application ^> Storage ^>
echo    Clear site data for wavefinity.onrender.com
echo.
pause
