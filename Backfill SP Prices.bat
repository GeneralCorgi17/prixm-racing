@echo off
cd /d "%~dp0"
echo === Prixm SP Price Backfill ===
echo.
echo Re-fetching Racing Post results for all May 2026+ dates missing SP...
echo This will update results_history.json and rebuild qualifying_picks.xlsx
echo.
python scripts\results_fetcher.py --backfill-sp --debug
echo.
pause
