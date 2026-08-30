@echo off
title AutoApply - Greenhouse Job Bot
cd /d "%~dp0"

echo ============================================
echo   AutoApply - Greenhouse Job Bot
echo   Dynamic Scraper & Auto-Applier Engine
echo   Press Ctrl+C to stop at any time
echo ============================================
echo.

set PYTHONIOENCODING=utf-8

:loop
echo [%date% %time%] 🔍 Step 1: Running Dynamic Greenhouse Job Scraper...
python scrape_greenhouse.py --min-score 50

echo.
echo [%date% %time%] 🚀 Step 2: Running Auto-Applier...
python batch_apply_greenhouse.py

echo.
echo [%date% %time%] Cycle complete. Waiting 5 minutes before next cycle...
echo Press Ctrl+C to stop, or close this window.
timeout /t 300 /nobreak >nul
goto loop
