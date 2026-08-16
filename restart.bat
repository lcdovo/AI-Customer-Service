@echo off
chcp 65001 >nul
title Customer Service System - Restart
echo ========================================
echo   Customer Service System - Restart
echo ========================================
echo.

echo [1/3] Stopping all services...
call %~dp0stop.bat
if errorlevel 1 (
    echo [WARN] Stop encountered issues, continuing...
)

echo.
echo [2/3] Waiting for services to fully stop...
timeout /t 5 /nobreak >nul

echo.
echo [3/3] Starting all services...
call %~dp0start.bat

echo.
echo ========================================
echo   Restart complete!
echo ========================================
pause