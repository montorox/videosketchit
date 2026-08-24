@echo off
setlocal
cd /d "%~dp0"

if not exist "start-videosketchit.bat" (
    echo Startup file start-videosketchit.bat was not found.
    pause
    exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
    echo Python environment was not found. Please finish installation first.
    pause
    exit /b 1
)

where npm.cmd >nul 2>nul
if errorlevel 1 (
    echo Node.js and npm were not found. Please install Node.js first.
    pause
    exit /b 1
)

if not exist "web\node_modules" (
    echo Frontend dependencies were not found. Run npm install in the web folder first.
    pause
    exit /b 1
)

call "%~dp0start-videosketchit.bat"
exit /b %errorlevel%
