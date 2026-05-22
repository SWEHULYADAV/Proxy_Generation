@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0"

set "CONFIG_FILE=proxy-service-config.env"

if not exist "venv\Scripts\python.exe" (
  echo Missing venv\Scripts\python.exe
  echo.
  echo First do your own install flow:
  echo   python -m venv venv
  echo   venv\Scripts\pip install -r requirements.txt
  echo.
  echo Then run this setup again.
  pause
  exit /b 1
)

echo Checking core Python dependencies...
venv\Scripts\python.exe -c "import aiohttp, aiohttp_socks, requests, rich"
if errorlevel 1 (
  echo Core dependencies are not installed in the virtual environment.
  echo.
  echo Run:
  echo   venv\Scripts\pip install -r requirements.txt
  echo.
  echo Then run this setup again.
  pause
  exit /b 1
)

if exist "proxy-service-config.bat" (
  echo Migrating old proxy-service-config.bat to %CONFIG_FILE%...
  call "proxy-service-config.bat"
  > "%CONFIG_FILE%" (
    set PROXY_SERVICE_HOST
    set PROXY_SERVICE_API_PORT
    set PROXY_SERVICE_TUNNEL_PORT
    set PROXY_SERVICE_API_KEY
    set PROXY_SERVICE_TUNNEL_KEY
    set PROXY_SERVICE_TUNNEL_USER
    set PROXY_SERVICE_WARMUP
    set PROXY_SERVICE_LOG_REQUESTS
    set PROXY_SERVICE_OUTPUT_ROOT
  )
  del /f /q "proxy-service-config.bat" >nul 2>nul
)

if exist "%CONFIG_FILE%" goto config_ready

:create_new_config

echo.
echo First-time personal setup
echo.
set "PROXY_SERVICE_HOST=127.0.0.1"
set "PROXY_SERVICE_API_PORT=1712"
set "PROXY_SERVICE_TUNNEL_PORT=1909"
set "PROXY_SERVICE_TUNNEL_USER=proxy"
set "PROXY_SERVICE_WARMUP=1"
set "PROXY_SERVICE_LOG_REQUESTS=1"
set "PROXY_SERVICE_OUTPUT_ROOT=output"

set "PROXY_SERVICE_API_KEY="
set /p PROXY_SERVICE_API_KEY=Enter your API key for REST API access (leave blank to auto-generate): 
set "PROXY_SERVICE_API_KEY=!PROXY_SERVICE_API_KEY: =!"
if "!PROXY_SERVICE_API_KEY!"=="" (
  for /f "usebackq delims=" %%A in (`powershell -NoProfile -Command "[guid]::NewGuid().ToString('N')"`) do set "PROXY_SERVICE_API_KEY=%%A"
)

set "PROXY_SERVICE_TUNNEL_KEY="
set /p PROXY_SERVICE_TUNNEL_KEY=Enter your tunnel proxy password (leave blank to auto-generate): 
set "PROXY_SERVICE_TUNNEL_KEY=!PROXY_SERVICE_TUNNEL_KEY: =!"
if "!PROXY_SERVICE_TUNNEL_KEY!"=="" (
  for /f "usebackq delims=" %%A in (`powershell -NoProfile -Command "[guid]::NewGuid().ToString('N')"`) do set "PROXY_SERVICE_TUNNEL_KEY=%%A"
)

set "INPUT_TUNNEL_USER="
set /p INPUT_TUNNEL_USER=Enter tunnel username (default: proxy): 
set "INPUT_TUNNEL_USER=!INPUT_TUNNEL_USER: =!"
if defined INPUT_TUNNEL_USER set "PROXY_SERVICE_TUNNEL_USER=!INPUT_TUNNEL_USER!"

echo Creating local service config...
> "%CONFIG_FILE%" (
  set PROXY_SERVICE_HOST
  set PROXY_SERVICE_API_PORT
  set PROXY_SERVICE_TUNNEL_PORT
  set PROXY_SERVICE_API_KEY
  set PROXY_SERVICE_TUNNEL_KEY
  set PROXY_SERVICE_TUNNEL_USER
  set PROXY_SERVICE_WARMUP
  set PROXY_SERVICE_LOG_REQUESTS
  set PROXY_SERVICE_OUTPUT_ROOT
)

:config_ready
for /f "usebackq tokens=1,* delims==" %%A in ("%CONFIG_FILE%") do set "%%A=%%B"

if not defined PROXY_SERVICE_HOST goto reset_broken_config
if not defined PROXY_SERVICE_API_PORT goto reset_broken_config
if not defined PROXY_SERVICE_TUNNEL_PORT goto reset_broken_config
if not defined PROXY_SERVICE_TUNNEL_USER goto reset_broken_config
goto config_ok

:reset_broken_config
echo Existing config file is empty or invalid. Recreating it...
del /f /q "%CONFIG_FILE%" >nul 2>nul
goto create_new_config

:config_ok

echo.
echo Setup complete for Rahul Yadav (SWEHUL Yadav).
echo.
echo REST API:    http://!PROXY_SERVICE_HOST!:!PROXY_SERVICE_API_PORT!
echo Proxy URL:   http://!PROXY_SERVICE_HOST!:!PROXY_SERVICE_TUNNEL_PORT!
echo API Key:     !PROXY_SERVICE_API_KEY!
echo Tunnel User: !PROXY_SERVICE_TUNNEL_USER!
echo Tunnel Key:  !PROXY_SERVICE_TUNNEL_KEY!
echo.
echo Saved config file: %~dp0%CONFIG_FILE%
echo.
echo Use this next time:
echo   Start-Live-Proxies.bat
echo.
echo If you ever want to change ports or keys, edit %CONFIG_FILE%
echo.
pause
