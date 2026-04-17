@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0"

if /I "%~1"=="__child" goto child_entry

set "MODE=%~1"
if /I "%MODE%"=="live" goto launch_live_only
if /I "%MODE%"=="api" goto launch_api_only

echo Starting both services...
start "Proxy Generator Live" cmd /k ""%~f0" __child live"
start "Proxy Generator API" cmd /k ""%~f0" __child api"
exit /b 0

:launch_live_only
start "Proxy Generator Live" cmd /k ""%~f0" __child %*"
exit /b 0

:launch_api_only
start "Proxy Generator API" cmd /k ""%~f0" __child %*"
exit /b 0

:child_entry
set "MODE=%~2"
shift
shift
set "FORWARD_ARGS="

:collect_args
if "%~1"=="" goto args_ready
set "FORWARD_ARGS=!FORWARD_ARGS! "%~1""
shift
goto collect_args

:args_ready
if not exist "venv\Scripts\python.exe" (
  echo Missing virtual environment. Create it and install requirements first.
  pause
  exit /b 1
)

if exist "active_proxies.json" del /f /q "active_proxies.json" >nul 2>nul
if exist "working_proxies.txt" del /f /q "working_proxies.txt" >nul 2>nul
if exist "working_proxies.json" del /f /q "working_proxies.json" >nul 2>nul

if /I "%MODE%"=="live" goto run_live
if /I "%MODE%"=="api" goto run_api

echo Invalid mode: %MODE%
pause
exit /b 1

:run_live
title Proxy Generator Live
echo Starting live proxy window...
echo.
venv\Scripts\python.exe -u Live-proxies.py --output-root "%~dp0output" !FORWARD_ARGS!
echo.
echo Live proxy session ended.
pause
exit /b 0

:run_api
title Proxy Generator API
echo Starting local proxy API...
echo.
venv\Scripts\python.exe -u Proxy-api.py --host 0.0.0.0 --tunnel-host 0.0.0.0 --output-root "%~dp0output" !FORWARD_ARGS!
echo.
echo Proxy API stopped.
pause
