@echo off
cd /d "%~dp0"

:: Phone simulator: runs the real app at phone size (public or owner view) before committing / pushing.
curl -s --max-time 1 http://localhost:7432/api/health >nul 2>&1
if not %ERRORLEVEL%==0 (
    start /min "Prixm DB" python "scripts\db_server.py"
    timeout /t 2 /nobreak >nul
)
start "" "%~dp0phone_preview.html"
