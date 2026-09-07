@echo off
setlocal

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0run_windows.ps1"

if errorlevel 1 (
    echo.
    echo TingPing stopped with an error. Press any key to close this window.
    pause >nul
)