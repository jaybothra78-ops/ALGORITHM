@echo off
title STRATLAB - Algorithmic Stock Screener & Trading Terminal
cd /d "%~dp0"

echo ========================================================
echo   Starting ALGORITHM Local Trading Server...
echo ========================================================
echo.
echo  Web Dashboard: http://localhost:8000
echo  Press Ctrl+C in this window anytime to stop the server.
echo.

:: Open browser after 2 seconds
start "" http://localhost:8000

python main.py

pause
