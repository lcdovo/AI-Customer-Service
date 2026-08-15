@echo off
chcp 65001 >nul
title Customer Service System - Stop
echo ========================================
echo   Customer Service System - Stop
echo ========================================
echo.

docker info >nul 2>&1
if errorlevel 1 (
    echo [INFO] Docker is not running, nothing to stop.
    pause
    exit /b 0
)

echo [1/2] Stopping all services (data volumes preserved)...
echo.
docker compose down
if errorlevel 1 (
    echo [WARN] Some services failed to stop, forcing...
    docker compose down --remove-orphans
)

echo.
echo [2/2] Cleaning residual containers...
for /f "tokens=*" %%c in ('docker ps --filter "name=cs_" --format "{{.Names}}" 2^>nul') do (
    echo   Removing: %%c
    docker rm -f %%c >nul 2>&1
)

echo.
echo ========================================
echo   System stopped!
echo ----------------------------------------
echo   Data volumes are preserved.
echo   To remove all data, run:
echo     docker compose down -v
echo ========================================
echo.
pause