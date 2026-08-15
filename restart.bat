@echo off
chcp 65001 >nul
title Customer Service System - Restart
echo ========================================
echo   Customer Service System - Restart
echo ========================================
echo.

call %~dp0stop.bat
echo.
echo Waiting for services to fully stop...
timeout /t 3 /nobreak >nul
echo.
call %~dp0start.bat