@echo off
REM Starts the demo environment: Dify (Docker, outside this repo) and this repo's own
REM containers (the MCP server + the web client, both docker-compose.yml, both
REM restart: unless-stopped -- neither needs a terminal window kept open).
REM Double-click this file, or run it from cmd: scripts\start_demo.bat
REM
REM One-time setup this script assumes is already done: see docs/dify_setup.md,
REM sections A1 (deploy Dify) and A3-A6 (admin account, model, MCP connection, app).
REM Needs curl.exe and ping (both built into Windows 10/11).

setlocal enabledelayedexpansion

set "DIFY_DIR=%USERPROFILE%\dify\docker"
set "REPO_DIR=%~dp0.."

echo == 1/3: Docker Desktop + Dify ==
docker info >nul 2>&1
if not errorlevel 1 goto docker_ready

REM Not running: start it and wait. This whole branch, including the :docker_wait loop, is
REM kept out of any parenthesised if-block -- a goto/label inside one is fragile in cmd.exe.
echo Docker Desktop is not running yet; starting it ...
if not exist "C:\Program Files\Docker\Docker\Docker Desktop.exe" (
    echo Docker Desktop was not found at "C:\Program Files\Docker\Docker\Docker Desktop.exe".
    echo Start it yourself, then re-run this script.
    exit /b 1
)
start "" "C:\Program Files\Docker\Docker\Docker Desktop.exe"
set /a DTRIES=0
:docker_wait
REM ping-based sleep: the "timeout" command needs a real console and fails ("Input
REM redirection is not supported") when this script runs with none attached (e.g. from a
REM scheduler); "ping -n 6 127.0.0.1" waits ~5s and works either way.
ping -n 6 127.0.0.1 >nul
docker info >nul 2>&1
if not errorlevel 1 goto docker_ready
set /a DTRIES+=1
if !DTRIES! GEQ 36 (
    echo Docker Desktop did not become ready within 180 seconds.
    exit /b 1
)
goto docker_wait

:docker_ready
echo Docker Desktop is running.

if not exist "%DIFY_DIR%" (
    echo Dify docker directory not found: %DIFY_DIR%
    echo Deploy Dify first -- see docs\dify_setup.md, section A1.
    exit /b 1
)
pushd "%DIFY_DIR%"
docker compose up -d
if errorlevel 1 (
    echo docker compose up -d failed in %DIFY_DIR%
    popd
    exit /b 1
)
popd

echo.
echo == 2/3: this repo's containers (MCP server + web client) ==
pushd "%REPO_DIR%"
if not exist ".env" (
    if exist ".env.example" (
        echo No .env file found; copying .env.example. Edit it to add your DEEPSEEK_API_KEY
        echo if you want run_adjudication and paid queries to work, then re-run this script.
        copy /y ".env.example" ".env" >nul
    )
)
docker compose up -d
if errorlevel 1 (
    echo docker compose up -d failed in %REPO_DIR%
    popd
    exit /b 1
)
popd

echo.
echo == 3/3: waiting for all three services ==
call :wait_for "http://localhost" "Dify"
call :wait_for "http://127.0.0.1:8765/mcp" "MCP server"
call :wait_for "http://127.0.0.1:8000/" "Web client"

echo.
echo == URLs ==
echo Dify:        http://localhost   (first run: create the admin account at http://localhost/install)
echo MCP server:  http://127.0.0.1:8765/mcp   (add it in Dify as http://host.docker.internal:8765/mcp)
echo Web client:  http://127.0.0.1:8000/
echo.
echo To stop everything this script started: scripts\stop_demo.bat
exit /b 0

:wait_for
set "WURL=%~1"
set "WLABEL=%~2"
set /a WCOUNT=0
echo Waiting for %WLABEL% (%WURL%) ...
:wait_for_loop
curl.exe -s -o nul --max-time 5 %WURL% < nul 2>nul
if not errorlevel 1 (
    echo   %WLABEL% is up.
    goto :eof
)
set /a WCOUNT+=1
if !WCOUNT! GEQ 100 (
    echo   WARNING: %WLABEL% did not respond within the timeout. Check "docker compose ps"
    echo   and "docker compose logs" in the relevant directory.
    goto :eof
)
ping -n 4 127.0.0.1 >nul
goto wait_for_loop
