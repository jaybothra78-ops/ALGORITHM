@echo off
setlocal
title ALGORITHM - Quantitative Trading Terminal
color 0A

echo =====================================================================
echo   Starting ALGORITHM Trading Engine and Local Web Dashboard
echo =====================================================================
echo.

:: 1. Locate the ALGORYTHM project folder
set "APP_DIR="
if exist "%~dp0main.py" (
    set "APP_DIR=%~dp0"
) else if exist "%~dp0ALGORYTHM\main.py" (
    set "APP_DIR=%~dp0ALGORYTHM"
) else if exist "C:\Users\jaybo\OneDrive\Desktop\ALGORYTHM\main.py" (
    set "APP_DIR=C:\Users\jaybo\OneDrive\Desktop\ALGORYTHM"
) else (
    echo [ERROR] Could not find ALGORYTHM folder with main.py!
    echo Please make sure the ALGORYTHM folder is on your Desktop.
    pause
    exit /b 1
)

:: Strip trailing backslash if present
if "%APP_DIR:~-1%"=="\" set "APP_DIR=%APP_DIR:~0,-1%"

cd /d "%APP_DIR%"
echo Working Directory: %APP_DIR%

:: 2. Locate Python executable (prefer .venv)
set "PY_CMD="
if exist "%APP_DIR%\.venv\Scripts\python.exe" (
    set "PY_CMD=%APP_DIR%\.venv\Scripts\python.exe"
    echo [OK] Using Virtual Environment Python
) else if exist "C:\Users\jaybo\AppData\Local\Python\pythoncore-3.14-64\python.exe" (
    set "PY_CMD=C:\Users\jaybo\AppData\Local\Python\pythoncore-3.14-64\python.exe"
    echo [OK] Using Python 3.14
) else (
    set "PY_CMD=python"
    echo [OK] Using Default Python
)

:: 3. Free port 8000 if already in use
for /f "tokens=5" %%p in ('netstat -aon 2^>nul ^| findstr /r ":8000.*LISTENING"') do (
    echo Freeing occupied port 8000 (PID %%p)
    taskkill /f /pid %%p >nul 2>&1
)

echo.
echo Starting web server on http://localhost:8000
echo Opening your browser in 4 seconds
echo.
echo *********************************************************************
echo   IMPORTANT: KEEP THIS BLACK WINDOW OPEN!
echo   The server runs inside this window. If you close it, the app stops.
echo   To stop the server anytime: press Ctrl+C or close this window.
echo *********************************************************************
echo.

:: 4. Launch browser in background after 4 seconds
start "" cmd /c "timeout /t 4 /nobreak >nul && start http://localhost:8000"

:: 5. Run FastAPI server
"%PY_CMD%" main.py

if errorlevel 1 (
    echo.
    echo =====================================================================
    echo   [ERROR] Server stopped with error code %errorlevel%
    echo =====================================================================
    pause
) else (
    echo.
    echo Server has stopped.
    pause
)
