@echo off
cd /d "%~dp0"

:: Check if server already running
curl -s --max-time 1 http://localhost:7432/api/health >nul 2>&1
if %ERRORLEVEL%==0 (
    echo Prixm DB server already running.
) else (
    echo Starting Prixm DB server...
    start /min "Prixm DB" python "scripts\db_server.py"
    timeout /t 2 /nobreak >nul
)

start "" "%~dp0daily_racing_analyzer.html"
