@echo off
cd /d "%~dp0"
echo ================================
echo   Prixm Racecard Fetcher
echo ================================
echo.
echo  Checking today's availability...
echo.
python racecard_fetcher.py --probe
echo.
echo --------------------------------
echo   [1] Today's races
echo   [2] Tomorrow's races
echo   [3] Day after tomorrow
echo   [4] Specific date
echo --------------------------------
echo.
set /p choice="Select option (1-4): "

if "%choice%"=="1" goto TODAY
if "%choice%"=="2" goto TOMORROW
if "%choice%"=="3" goto DAY_AFTER
if "%choice%"=="4" goto SPECIFIC
echo Invalid option.
goto END

:TODAY
echo.
python racecard_fetcher.py
goto END

:TOMORROW
echo.
python racecard_fetcher.py --tomorrow
goto END

:DAY_AFTER
echo.
python -c "import datetime;print((datetime.date.today()+datetime.timedelta(days=2)).isoformat())" > "%TEMP%\prixm_date.txt"
set /p FETCHDATE=<"%TEMP%\prixm_date.txt"
python racecard_fetcher.py --date %FETCHDATE%
goto END

:SPECIFIC
echo.
set /p FETCHDATE="Enter date (YYYY-MM-DD): "
echo.
python racecard_fetcher.py --date %FETCHDATE%
goto END

:END
echo.
pause
