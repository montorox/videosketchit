@echo off
setlocal
cd /d "%~dp0"

if not exist "start-webapp.ps1" (
    echo ERROR: start-webapp.ps1 was not found.
    pause
    exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
    echo ERROR: Python dependencies are not installed.
    echo Follow the Windows installation steps in README.md first.
    pause
    exit /b 1
)

where npm.cmd >nul 2>nul
if errorlevel 1 (
    echo ERROR: Node.js and npm were not found on PATH.
    echo Install Node.js 22, open a new terminal, and try again.
    pause
    exit /b 1
)

where ffmpeg.exe >nul 2>nul
if errorlevel 1 (
    echo ERROR: FFmpeg was not found on PATH.
    echo Install FFmpeg, open a new terminal, and try again.
    pause
    exit /b 1
)

where codex.exe >nul 2>nul
if errorlevel 1 (
    where codex.cmd >nul 2>nul
    if errorlevel 1 (
        echo ERROR: Codex CLI was not found on PATH.
        echo Install Codex and run "codex login" before starting this app.
        pause
        exit /b 1
    )
)

if not exist "web\node_modules" (
    echo ERROR: Frontend dependencies are not installed.
    echo Follow the Windows installation steps in README.md first.
    pause
    exit /b 1
)

echo Starting CS Board Codex Edition...
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0start-webapp.ps1"
if errorlevel 1 (
    echo.
    echo Startup failed. See .cs-board-codex\launcher-error.log for details.
    pause
    exit /b 1
)

exit /b 0
