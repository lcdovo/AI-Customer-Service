@echo off
chcp 65001 >nul
title Customer Service System - Status
echo ========================================
echo   Customer Service System - Status
echo ========================================
echo.

REM Detect Docker Compose version
docker compose version >nul 2>&1
if errorlevel 1 (
    set "COMPOSE_CMD=docker-compose"
) else (
    set "COMPOSE_CMD=docker compose"
)

docker info >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Docker is not running.
    echo.
    echo --- Port Usage ---
    netstat -ano | findstr "LISTENING" | findstr /R ":8000 :3306 :6379 :19531 :9002 :2380"
    echo.
    echo --- Local App Check ---
    curl -s http://localhost:8000/health 2>nul
    if errorlevel 1 echo   (Application not ready)
    pause
    exit /b 1
)

echo --- Container Status ---
%COMPOSE_CMD% ps

echo.
echo --- Port Usage ---
netstat -ano | findstr "LISTENING" | findstr /R ":8000 "

netstat -ano | findstr "LISTENING" | findstr /R ":3306 "

netstat -ano | findstr "LISTENING" | findstr /R ":6379 "

netstat -ano | findstr "LISTENING" | findstr /R ":19531 "

netstat -ano | findstr "LISTENING" | findstr /R ":9002 "

netstat -ano | findstr "LISTENING" | findstr /R ":2380 "

echo.
echo --- Health Check ---
curl -s http://localhost:8000/health 2>nul
if errorlevel 1 echo   (Application not ready)

echo.
echo.
pause