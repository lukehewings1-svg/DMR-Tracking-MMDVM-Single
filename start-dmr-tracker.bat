@echo off
title DMR Tracker Launcher
set "ROOT=%~dp0"

sc query MongoDB | find "RUNNING" >nul || (
  echo MongoDB is not running - trying to start it...
  net start MongoDB >nul 2>&1 || echo Could not start MongoDB. Open services.msc and start "MongoDB Server".
)

start "DMR Tracker - Backend" /D "%ROOT%backend" cmd /c run-backend.bat
start "DMR Tracker - Frontend" /D "%ROOT%frontend" cmd /k "set BROWSER=none&& yarn start"

echo Starting DMR Tracker, the browser will open when it is ready...
powershell -NoProfile -Command "$t=0; while ($t -lt 240) { try { Invoke-WebRequest -UseBasicParsing http://localhost:3000 -TimeoutSec 2 | Out-Null; break } catch { Start-Sleep 2; $t+=2 } }"
start "" http://localhost:3000
exit
