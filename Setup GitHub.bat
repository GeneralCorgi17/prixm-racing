@echo off
cd /d "%~dp0"
echo.
echo ===================================================
echo  Prixm - GitHub Pages Setup (run ONCE)
echo ===================================================
echo.
echo Before running this:
echo   1. Create a NEW repo on github.com (e.g. "prixm-racing")
echo   2. Make it PUBLIC (required for free GitHub Pages)
echo   3. Do NOT add README or .gitignore on GitHub
echo   4. Copy the repo URL (e.g. https://github.com/yourname/prixm-racing.git)
echo.
set /p REPO_URL="Paste your GitHub repo URL here: "
echo.

git remote remove origin 2>nul
git remote add origin %REPO_URL%

git add .
git commit -m "init: Prixm Racing Analyzer"
git branch -M main
git push -u origin main

if errorlevel 1 (
    echo.
    echo Push failed. You may need to authenticate:
    echo   - Install GitHub CLI: winget install GitHub.cli
    echo   - Then run: gh auth login
    echo   - Then re-run this bat file
    pause
    exit /b 1
)

echo.
echo ===================================================
echo  Pushed! Now enable GitHub Pages:
echo.
echo   1. Go to your repo on github.com
echo   2. Settings ^> Pages
echo   3. Source: "Deploy from a branch"
echo   4. Branch: main  /  Folder: / (root)
echo   5. Save
echo.
echo   Your URL will be:
echo   https://[your-username].github.io/prixm-racing/
echo.
echo   Takes ~1 minute to go live.
echo ===================================================
echo.
pause
