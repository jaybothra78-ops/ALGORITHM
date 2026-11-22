@echo off
setlocal enabledelayedexpansion
title ALGORITHM - Quantitative Trading Terminal
cd /d "%~dp0"

echo =====================================================================
echo   Starting ALGORITHM Trading Engine & Local Web Dashboard...
echo =====================================================================
echo.

:: 1. Detect Python
if exist "%~dp0.venv\Scripts\python.exe" (
    set "PY_CMD=%~dp0.venv\Scripts\python.exe"
    echo [OK] Using Virtual Environment Python
) else (
    set "PY_CMD=python"
    echo [OK] Using System Python
)

echo.
echo Starting web server on http://localhost:8000 ...
echo Opening browser in 4 seconds...
echo.
echo *********************************************************************
echo   NOTE: KEEP THIS BLACK WINDOW OPEN!
echo   The server runs inside this window. If you close it, the app stops.
echo   To stop the server anytime: press Ctrl+C or close this window.
echo *********************************************************************
echo.

:: 2. Launch browser in background after 4 seconds (giving server time to boot)
start "" cmd /c "timeout /t 4 /nobreak >nul && start http://localhost:8000"

:: 3. Run FastAPI server
"!PY_CMD!" main.py

if errorlevel 1 (
    echo.
    echo =====================================================================
    echo   [ERROR] The server encountered an issue and stopped.
    echo =====================================================================
    pause
)
