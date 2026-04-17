@echo off
REM PoolAIssistant Brain - Database Sync Runner
REM Runs automatically on Windows login via Scheduled Task

cd /d "%~dp0"
python db_sync.py
