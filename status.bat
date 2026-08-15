@echo off
chcp 65001 >nul
title Customer Service System - Status
echo ========================================
echo   Customer Service System - Status
echo ========================================
echo.

docker info >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Docker is not running.
    pause
    exit /b 1
)

echo --- Container Status ---
docker compose ps

echo.
echo --- Port Usage ---
netstat -ano | findstr "LISTENING" | findstr ":8000 :3306 :6379 :19531 :9002 :2380"

echo.
echo --- Health Check ---
curl -s http://localhost:8000/health 2>nul
if errorlevel 1 echo   (Application not ready)

echo.
echo.
pause