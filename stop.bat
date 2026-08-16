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

echo [1/3] Stopping all services (data volumes preserved)...
echo.

REM Try docker compose (V2) first, fall back to docker-compose (V1)
docker compose down 2>nul
if not errorlevel 1 goto stop_done
docker-compose down 2>nul
if not errorlevel 1 goto stop_done
echo [WARN] Standard stop failed, forcing with --remove-orphans...
docker compose down --remove-orphans 2>nul
if not errorlevel 1 goto stop_done
docker-compose down --remove-orphans 2>nul
:stop_done

echo.
echo [2/3] Waiting for containers to fully stop...
timeout /t 3 /nobreak >nul

echo.
echo [3/3] Cleaning residual containers...
set "CLEANED=0"
for /f "tokens=*" %%c in ('docker ps -a --filter "name=cs_" --format "{{.Names}}" 2^>nul') do (
    if not "%%c"=="" (
        echo   Removing: %%c
        docker rm -f %%c >nul 2>&1
        set "CLEANED=1"
    )
)
if "%CLEANED%"=="0" (
    echo   No residual containers found.
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