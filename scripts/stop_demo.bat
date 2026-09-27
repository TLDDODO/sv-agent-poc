@echo off
REM Stops what scripts\start_demo.bat started: this repo's containers (MCP server + web
REM client) and Dify's containers. Uses "docker compose stop", not "down": containers and
REM their data are kept, so start_demo.bat can bring everything back quickly with "up -d".
REM To remove the containers as well, run "docker compose down" by hand in each directory.
REM Double-click this file, or run it from cmd: scripts\stop_demo.bat

setlocal enabledelayedexpansion

set "DIFY_DIR=%USERPROFILE%\dify\docker"
set "REPO_DIR=%~dp0.."

echo == Stopping this repo's containers (MCP server + web client) ==
pushd "%REPO_DIR%"
docker compose stop
popd

echo.
echo == Stopping Dify (docker compose stop -- containers and data are kept) ==
if exist "%DIFY_DIR%" (
    pushd "%DIFY_DIR%"
    docker compose stop
    popd
) else (
    echo Dify docker directory not found: %DIFY_DIR%; skipping.
)

echo.
echo Done.
