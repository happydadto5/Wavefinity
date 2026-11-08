@echo off
rem Clean launch: wipes Wavefinity's saved data (test data, generated files), then launches.
powershell -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "%~dp0launch_wavefinity.ps1" -Clean
