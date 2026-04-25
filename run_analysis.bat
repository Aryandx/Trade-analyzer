@echo off
title Indian Market Analyzer
echo.
echo  ====================================================
echo    Indian Stock Market Analyzer  -  Budget: 5000 INR
echo  ====================================================
echo.
echo  Starting full analysis (100+ stocks, 3y history)...
echo  This takes 30-60 minutes on first run.
echo  Next runs are faster (data is cached for 18 hours).
echo.
cd /d "%~dp0"
python -X utf8 main.py
echo.
pause
