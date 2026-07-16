@echo off
title Monko Suite AI Macro Desk
echo ==============================================
echo Monko AI Macro Desk Local Server
echo ==============================================
echo.
echo [1/2] Opening dashboard in your default browser...
start "" "http://127.0.0.1:5000"
echo.
echo [2/2] Starting Flask local server engine...
py -3.13 app.py
pause
