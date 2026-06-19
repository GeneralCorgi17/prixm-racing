@echo off
cd /d "%~dp0"
echo.
echo ===================================================
echo  Prixm - Push Update to GitHub Pages
echo ===================================================
echo.

:: Check git is available
git --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: git not found. Install git from https://git-scm.com
    pause
    exit /b 1
)

:: Check remote is configured
git remote get-url origin >nul 2>&1
if errorlevel 1 (
    echo ERROR: No GitHub remote configured.
    echo Run Setup GitHub.bat first.
    pause
    exit /b 1
)

:: Stage data files
echo Staging data files...
git add results_history.json
git add results_history.js
git add daily_race_data.json
git add daily_racing_analyzer.html
git add calibrations.json
git add race_data/

:: Stage UI/engine files if changed
git add engine/ 2>nul
git add CLAUDE.md 2>nul
git add index.html
git add robots.txt

:: Check if anything to commit
git diff --cached --quiet
if %errorlevel%==0 (
    echo No changes to push - already up to date.
    pause
    exit /b 0
)

:: Commit with timestamp
for /f "tokens=1-3 delims=/ " %%a in ('date /t') do set TODAY=%%c-%%b-%%a
for /f "tokens=1-2 delims=: " %%a in ('time /t') do set NOW=%%a:%%b
git commit -m "data: update %TODAY% %NOW%"

:: Push
echo.
echo Pushing to GitHub...
git push origin main
if errorlevel 1 (
    echo.
    echo ERROR: Push failed. Check internet connection or GitHub auth.
    pause
    exit /b 1
)

echo.
echo ===================================================
echo  Done! GitHub Pages will update in ~1 minute.
echo ===================================================
echo.
pause
