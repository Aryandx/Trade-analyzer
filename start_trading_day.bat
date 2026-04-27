@echo off
cd /d "C:\Users\aryxn\stock_analyzer"

:: Window 1 — Morning scan (picks today's stocks, updates website)
start "Morning Scanner" cmd /k "python morning_scanner.py --capital 20000 & echo. & echo Done. Run --live at 9:30 AM: python morning_scanner.py --live --capital 20000 & pause"

:: Small delay so both windows don't fight over terminal
timeout /t 5 /nobreak >nul

:: Window 2 — Auto-push daemon (keeps website updated every 5 min all day)
start "Auto Push Daemon" cmd /k "python auto_push.py --capital 20000"
