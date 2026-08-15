@echo off
chcp 65001 >nul
title Customer Service System - Start
echo ========================================
echo   Customer Service System - Start
echo ========================================
echo.

docker info >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Docker is not running. Please start Docker Desktop first.
    pause
    exit /b 1
)

echo [1/4] Building and starting all services...
echo.
docker compose up -d --build
if errorlevel 1 (
    echo [ERROR] Failed to start services.
    pause
    exit /b 1
)

echo.
echo [2/4] Waiting for services to be ready...
timeout /t 5 /nobreak >nul

echo.
echo [3/4] Checking service status...
echo.
docker compose ps

echo.
echo [4/4] Verifying application...
timeout /t 3 /nobreak >nul

curl -s http://localhost:8000/health >nul 2>&1
if errorlevel 1 (
    echo [WARN] Application may still be starting, please wait...
) else (
    echo [OK] Application is ready!
)

echo.
echo ========================================
echo   System started successfully!
echo ----------------------------------------
echo   Frontend:  http://localhost:8000
echo   API Docs:  http://localhost:8000/docs
echo   User:      user001 / password
echo   Admin:     admin / admin123
echo ========================================
echo.
echo Press any key to open browser...
pause >nul
start http://localhost:8000