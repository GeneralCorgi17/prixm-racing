@echo off
cd /d "%~dp0"
echo === Prixm Qualifying Picks Exporter ===
echo.
echo Building combined qualifying_picks.xlsx from all May 2026 onwards dates...
echo.
python scripts\qualifying_exporter.py --scan
echo.
pause
