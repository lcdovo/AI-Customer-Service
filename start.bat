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

REM Detect Docker Compose version (V2: "docker compose", V1: "docker-compose")
docker compose version >nul 2>&1
if errorlevel 1 (
    docker-compose version >nul 2>&1
    if errorlevel 1 (
        echo [ERROR] Docker Compose not found. Please install Docker Compose.
        pause
        exit /b 1
    )
    set "COMPOSE_CMD=docker-compose"
    echo [INFO] Using Docker Compose V1
) else (
    set "COMPOSE_CMD=docker compose"
    echo [INFO] Using Docker Compose V2
)

echo.
echo [1/4] Building and starting all services...
echo.
%COMPOSE_CMD% up -d --build
if errorlevel 1 (
    echo [ERROR] Failed to start services.
    pause
    exit /b 1
)

echo.
echo [2/4] Waiting for services to be ready...
timeout /t 8 /nobreak >nul

echo.
echo [3/4] Checking service status...
echo.
%COMPOSE_CMD% ps

echo.
echo [4/4] Verifying application (with retries)...
set /a RETRY=0
:health_check
set /a RETRY+=1
curl -s http://localhost:8000/health >nul 2>&1
if not errorlevel 1 (
    echo [OK] Application is ready!
    goto start_done
)
if %RETRY% GEQ 10 (
    echo [WARN] Application health check timed out after 10 retries.
    echo        Services may still be starting, check with status.bat
    goto start_done
)
echo   Waiting... retry %RETRY%/10
timeout /t 3 /nobreak >nul
goto health_check

:start_done
echo.
echo ========================================
echo   System started successfully!
echo ----------------------------------------
echo   Frontend:  http://localhost:8000
echo   API Docs:  http://localhost:8000/docs
echo   Attu:      http://localhost:8080
echo              (Milvus Admin UI)
echo ----------------------------------------
echo   User:      user001 / password
echo   Admin:     admin / admin123
echo ========================================
echo.
echo Press any key to open browser...
pause >nul
start http://localhost:8000
echo   Opening Attu in 3 seconds...
timeout /t 3 /nobreak >nul
start http://localhost:8080