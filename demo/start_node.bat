@echo off
:: ═══════════════════════════════════════════════════════
::  D-Cloud Node Server — Windows One-Click Starter
::  Run this on each machine.
::
::  Usage:  start_node.bat [node-id] [port]
::  Example: start_node.bat node1 8001
::
::  Default: node1 on port 8001
:: ═══════════════════════════════════════════════════════

set NODE_ID=%1
set PORT=%2

if "%NODE_ID%"=="" set NODE_ID=node1
if "%PORT%"=="" set PORT=8001

echo.
echo  ╔════════════════════════════════════════╗
echo  ║  D-Cloud Node Server — Windows         ║
echo  ║  Node: %NODE_ID%   Port: %PORT%              ║
echo  ╚════════════════════════════════════════╝
echo.

:: Check Python is available
python --version >nul 2>&1
if errorlevel 1 (
    echo  ERROR: Python not found. Install Python 3.8+ from https://python.org
    pause
    exit /b 1
)

:: Find node_server.py (one level up from demo\ folder)
set SCRIPT=%~dp0..\node_server.py
if not exist "%SCRIPT%" (
    echo  ERROR: node_server.py not found at %SCRIPT%
    pause
    exit /b 1
)

echo  Starting node server...
echo  This window must stay open while the demo runs.
echo  Press Ctrl+C to stop.
echo.

python "%SCRIPT%" --port %PORT% --node-id %NODE_ID% --host 0.0.0.0
pause
