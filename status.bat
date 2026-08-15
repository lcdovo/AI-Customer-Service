@echo off
chcp 65001 >nul
title 智能客服系统 - 查看状态
echo ========================================
echo   智能客服系统 - 服务状态
echo ========================================
echo.

docker info >nul 2>&1
if errorlevel 1 (
    echo [错误] Docker 未启动
    pause
    exit /b 1
)

echo 当前容器状态:
echo.
docker compose ps

echo.
echo --- 端口占用情况 ---
netstat -ano | findstr ":8000 :3306 :6379 :19531 :9002"

echo.
echo --- 健康检查 ---
curl -s http://localhost:8000/health 2>nul
if errorlevel 1 echo   (应用未就绪)

echo.
echo.
pause