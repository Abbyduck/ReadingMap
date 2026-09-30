@echo off
setlocal

set "ROOT=%~dp0"

if not exist "%ROOT%backend\.venv\Scripts\python.exe" (
    echo [Reading Map] Backend virtual environment is missing.
    echo Follow the setup steps in README.md first.
    pause
    exit /b 1
)

if not exist "%ROOT%backend\.env" (
    echo [Reading Map] backend\.env is missing.
    echo Follow the setup steps in README.md first.
    pause
    exit /b 1
)

if not exist "%ROOT%frontend\node_modules\vite\bin\vite.js" (
    echo [Reading Map] Frontend dependencies are missing.
    echo Run: cd frontend ^&^& npm ci
    pause
    exit /b 1
)

where npm.cmd >nul 2>&1
if errorlevel 1 (
    echo [Reading Map] npm is unavailable. Install Node.js and try again.
    pause
    exit /b 1
)

netstat -ano -p TCP | findstr /C:":8010 " | findstr /C:"LISTENING" >nul
if not errorlevel 1 (
    echo [Reading Map] Port 8010 is already in use. Close the existing backend window first.
    pause
    exit /b 1
)

netstat -ano -p TCP | findstr /C:":53180 " | findstr /C:"LISTENING" >nul
if not errorlevel 1 (
    echo [Reading Map] Port 53180 is already in use. Close the existing frontend window first.
    pause
    exit /b 1
)

start "Reading Map Backend" /D "%ROOT%backend" cmd /k ".venv\Scripts\python.exe manage.py runserver 127.0.0.1:8010"
start "Reading Map Frontend" /D "%ROOT%frontend" cmd /k "npm.cmd run dev"

echo [Reading Map] Started backend and frontend in separate windows.
echo Open http://127.0.0.1:53180 after the frontend is ready.
echo To stop, press Ctrl+C in each server window.
