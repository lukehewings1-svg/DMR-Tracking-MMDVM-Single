@echo off
title DMR Tracker - Backend
cd /d "%~dp0"
call venv\Scripts\activate.bat
:loop
uvicorn server:app --host 0.0.0.0 --port 8001
if %errorlevel%==3 (
  echo Update installed - restarting the backend...
  timeout /t 2 /nobreak >nul
  goto loop
)
echo Backend stopped (exit code %errorlevel%).
pause
