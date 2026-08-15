@echo off
chcp 65001 >nul
title 智能客服系统 - 一键停止
echo ========================================
echo   智能客服系统 - 一键停止脚本
echo ========================================
echo.

REM 检查 Docker 是否运行
docker info >nul 2>&1
if errorlevel 1 (
    echo [错误] Docker 未运行，无需停止
    pause
    exit /b 0
)

echo [1/2] 停止所有服务 (保留数据卷)...
echo.
docker compose down
if errorlevel 1 (
    echo [警告] 部分服务停止失败，尝试强制停止...
    docker compose down --remove-orphans
)

echo.
echo [2/2] 清理完成
timeout /t 2 /nobreak >nul

REM 检查是否有残留容器
for /f "tokens=*" %%c in ('docker ps --filter "name=cs_" --format "{{.Names}}" 2^>nul') do (
    echo [警告] 发现残留容器: %%c
    echo         正在清理...
    docker rm -f %%c >nul 2>&1
)

echo.
echo ========================================
echo   系统已停止!
echo ----------------------------------------
echo   数据卷已保留，重新启动后数据不变
echo   如需彻底清除数据，请运行:
echo     docker compose down -v
echo ========================================
echo.
pause