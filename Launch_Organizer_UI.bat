@echo off
rem Launch Wavefinity. Silent when fine; a message box appears only on a problem.
powershell -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "%~dp0launch_wavefinity.ps1"
