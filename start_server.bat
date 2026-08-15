@echo off
set MYSQL_HOST=localhost
set MYSQL_PORT=9999
set MYSQL_USER=root
set MYSQL_PASSWORD=
set MYSQL_DATABASE=sqlite+aiosqlite:///./test.db
set REDIS_HOST=localhost
set REDIS_PORT=9999
set REDIS_PASSWORD=
set REDIS_DB=0
set LLM_API_KEY=test-key
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
