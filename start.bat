@echo off
chcp 65001 >nul
title 智能客服系统 - 一键启动
echo ========================================
echo   智能客服系统 - 一键启动脚本
echo ========================================
echo.

REM 检查 Docker 是否运行
docker info >nul 2>&1
if errorlevel 1 (
    echo [错误] Docker 未启动，请先启动 Docker Desktop
    pause
    exit /b 1
)

echo [1/4] 构建并启动所有服务...
echo.
docker compose up -d --build
if errorlevel 1 (
    echo [错误] 服务启动失败
    pause
    exit /b 1
)

echo.
echo [2/4] 等待基础服务就绪 (etcd, minio, mysql, redis)...
timeout /t 5 /nobreak >nul

echo.
echo [3/4] 检查服务健康状态...
echo.
docker compose ps

echo.
echo [4/4] 验证应用服务...
timeout /t 3 /nobreak >nul

curl -s http://localhost:8000/health >nul 2>&1
if errorlevel 1 (
    echo [警告] 应用服务可能仍在启动中，请稍候刷新
) else (
    echo [成功] 应用服务已就绪!
)

echo.
echo ========================================
echo   系统启动完成!
echo ----------------------------------------
echo   前端页面: http://localhost:8000
echo   API 文档: http://localhost:8000/docs
echo   用户账号: user001 / password
echo   管理员:   admin / admin123
echo ========================================
echo.
echo 按任意键打开浏览器...
pause >nul
start http://localhost:8000