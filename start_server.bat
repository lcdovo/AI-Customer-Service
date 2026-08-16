@echo off
chcp 65001 >nul
title Customer Service System - Local Dev Server
echo ========================================
echo   Customer Service System - Local Dev
echo ========================================
echo.

REM Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python is not installed or not in PATH.
    echo         Please install Python 3.10+ and try again.
    pause
    exit /b 1
)

echo [1/3] Checking dependencies...
python -c "import fastapi, sqlalchemy, redis" >nul 2>&1
if errorlevel 1 (
    echo [WARN] Missing dependencies, installing...
    pip install -r requirements.txt
    if errorlevel 1 (
        echo [ERROR] Failed to install dependencies.
        pause
        exit /b 1
    )
) else (
    echo [OK] Dependencies are ready.
)

echo.
echo [2/3] Initializing local database (SQLite)...
set DATABASE_URL_OVERRIDE=sqlite+aiosqlite:///./test.db
set MYSQL_HOST=localhost
set MYSQL_PORT=3306
set MYSQL_USER=root
set MYSQL_PASSWORD=
set MYSQL_DATABASE=customer_service
set REDIS_HOST=localhost
set REDIS_PORT=6379
set REDIS_PASSWORD=
set REDIS_DB=0
set USE_MILVUS=false
set DEBUG=true

REM Initialize database (create tables + default users)
python -c "import asyncio; from app.utils.database import init_database; asyncio.run(init_database())" >nul 2>&1
if errorlevel 1 (
    echo [WARN] Database initialization failed, will retry on startup.
) else (
    echo [OK] Database initialized.
)

echo.
echo [3/3] Starting server on port 8000...
echo.
echo ========================================
echo   Frontend:  http://localhost:8000
echo   API Docs:  http://localhost:8000/docs
echo   User:      user001 / password
echo   Admin:     admin / admin123
echo   (SQLite mode - no Docker required)
echo ========================================
echo.
echo Press Ctrl+C to stop the server.
echo.

python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload