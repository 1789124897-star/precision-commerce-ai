@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ═══════════════════════════════════════
echo   电商 AI 助手 — 一键启动
echo ═══════════════════════════════════════
echo.
echo   FastAPI  : http://localhost:8000
echo   Swagger  : http://localhost:8000/docs
echo.
echo ═══════════════════════════════════════

start "FastAPI" cmd /k "title FastAPI ^& cd /d %cd% ^& uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload"
start "Celery" cmd /k "title Celery Worker ^& cd /d %cd% ^& celery -A app.core.celery_app worker --pool=solo --loglevel=info -Q video,ai,compose,scraper,default"
