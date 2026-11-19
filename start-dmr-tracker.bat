@echo off
title DMR Tracker Launcher
set "ROOT=%~dp0"

sc query MongoDB | find "RUNNING" >nul || (
  echo MongoDB is not running - trying to start it...
  net start MongoDB >nul 2>&1 || echo Could not start MongoDB. Open services.msc and start "MongoDB Server".
)

rem --- After an update, install any new dashboard packages ---
cd /d "%ROOT%frontend"
set "NEED_YARN=0"
if not exist node_modules\.dmr-stamp set "NEED_YARN=1"
if "%NEED_YARN%"=="0" powershell -NoProfile -Command "$s=(Get-Item node_modules\.dmr-stamp).LastWriteTime; if ((Get-Item package.json).LastWriteTime -gt $s -or (Get-Item yarn.lock).LastWriteTime -gt $s) { exit 1 }" || set "NEED_YARN=1"
if "%NEED_YARN%"=="1" (
  echo Installing dashboard packages after an update - this can take a few minutes...
  call yarn install || (echo yarn install failed - see the messages above. & pause & exit /b 1)
  type nul > node_modules\.dmr-stamp
)

rem --- After an update, install any new backend packages ---
cd /d "%ROOT%backend"
set "NEED_PIP=0"
if not exist venv\.dmr-stamp set "NEED_PIP=1"
if "%NEED_PIP%"=="0" powershell -NoProfile -Command "if ((Get-Item requirements-windows.txt).LastWriteTime -gt (Get-Item venv\.dmr-stamp).LastWriteTime) { exit 1 }" || set "NEED_PIP=1"
if "%NEED_PIP%"=="1" (
  echo Installing backend packages after an update...
  call venv\Scripts\python.exe -m pip install -r requirements-windows.txt || (echo pip install failed - see the messages above. & pause & exit /b 1)
  type nul > venv\.dmr-stamp
)

rem --- Build the dashboard when it's missing or the code changed ---
cd /d "%ROOT%frontend"
set "NEED_BUILD=0"
if not exist build\.same-origin set "NEED_BUILD=1"
if "%NEED_BUILD%"=="0" powershell -NoProfile -Command "$b=(Get-Item build\.same-origin).LastWriteTime; $n=(Get-ChildItem src,public -Recurse -File | Measure-Object LastWriteTime -Maximum).Maximum; if ($n -gt $b -or (Get-Item package.json).LastWriteTime -gt $b) { exit 1 }" || set "NEED_BUILD=1"
if "%NEED_BUILD%"=="1" (
  echo Building the dashboard - about a minute, only after updates...
  set "REACT_APP_SAME_ORIGIN=true"
  call yarn build || (echo Dashboard build failed - see the messages above. & pause & exit /b 1)
  type nul > build\.same-origin
)

start "DMR Tracker - Server" /D "%ROOT%backend" cmd /c run-backend.bat

echo Starting DMR Tracker, the browser will open when it is ready...
powershell -NoProfile -Command "$t=0; while ($t -lt 120) { try { Invoke-WebRequest -UseBasicParsing http://localhost:8001/ -TimeoutSec 2 | Out-Null; break } catch { Start-Sleep 2; $t+=2 } }"
start "" http://localhost:8001
exit
