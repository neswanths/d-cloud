@echo off
:: ═════════════════════════════════════════════════════
::  D-Cloud Bridge + UI Starter — Windows
::  Run this on the machine that hosts the bridge.
::
::  Before running: update api-bridge\.env with NODE_URLS
::  pointing to your 3 machine IPs.
:: ═════════════════════════════════════════════════════

set SCRIPT_DIR=%~dp0
set PROJECT_DIR=%SCRIPT_DIR%..
set BRIDGE_DIR=%PROJECT_DIR%\api-bridge
set FRONTEND_DIR=%PROJECT_DIR%\frontend

echo.
echo  ╔════════════════════════════════════════════╗
echo  ║  D-Cloud Bridge + UI Starter               ║
echo  ║  Bridge → http://localhost:3000            ║
echo  ║  UI     → http://localhost:5173            ║
echo  ╚════════════════════════════════════════════╝
echo.

:: ── Check .env exists ────────────────────────────────
if not exist "%BRIDGE_DIR%\.env" (
    echo  Creating .env from .env.example...
    copy "%BRIDGE_DIR%\.env.example" "%BRIDGE_DIR%\.env" >nul
    echo  IMPORTANT: Edit api-bridge\.env and set your NODE_URLS!
    echo  Example: NODE_URLS=http://192.168.1.10:8001,http://192.168.1.11:8001,http://192.168.1.12:8001
    echo.
    notepad "%BRIDGE_DIR%\.env"
)

:: ── Start FastAPI bridge in background ───────────────
echo  Starting FastAPI bridge on :3000...
start "D-Cloud Bridge" cmd /k "cd /d %BRIDGE_DIR% && .venv\Scripts\activate && uvicorn main:app --host 0.0.0.0 --port 3000 --reload"

:: Wait for bridge to come up
timeout /t 3 /nobreak >nul

:: ── Start frontend dev server ────────────────────────
echo  Starting frontend on :5173...
start "D-Cloud Frontend" cmd /k "cd /d %FRONTEND_DIR% && npm run dev"

:: Wait then open browser
timeout /t 4 /nobreak >nul
echo  Opening browser...
start "" http://localhost:5173

echo.
echo  ✅ D-Cloud demo is running!
echo     Bridge:   http://localhost:3000/api/health
echo     UI:       http://localhost:5173
echo.
echo  Close the Bridge and Frontend windows to shut down.
pause
