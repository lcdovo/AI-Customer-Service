@echo off
chcp 65001 >nul
title 智能客服系统 - 重启
echo ========================================
echo   智能客服系统 - 重启脚本
echo ========================================
echo.

call %~dp0stop.bat
echo.
echo 正在等待服务完全停止...
timeout /t 3 /nobreak >nul
echo.
call %~dp0start.bat