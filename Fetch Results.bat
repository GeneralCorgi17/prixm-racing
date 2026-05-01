@echo off
cd /d "%~dp0"
echo ====================================
echo   Prixm Results Fetcher
echo ====================================
echo.
echo ------------------------------------
echo   [1] Today's results
echo   [2] Yesterday's results
echo   [3] Day before yesterday
echo   [4] Specific date
echo ------------------------------------
echo.
set /p choice="Select option (1-4): "

if "%choice%"=="1" goto TODAY
if "%choice%"=="2" goto YESTERDAY
if "%choice%"=="3" goto DAY_BEFORE
if "%choice%"=="4" goto SPECIFIC
echo Invalid option.
goto END

:TODAY
echo.
python results_fetcher.py --debug
goto END

:YESTERDAY
echo.
python results_fetcher.py --yesterday --debug
goto END

:DAY_BEFORE
echo.
python -c "import datetime;print((datetime.date.today()-datetime.timedelta(days=2)).isoformat())" > "%TEMP%\prixm_res_date.txt"
set /p FETCHDATE=<"%TEMP%\prixm_res_date.txt"
python results_fetcher.py --date %FETCHDATE% --debug
goto END

:SPECIFIC
echo.
set /p FETCHDATE="Enter date (YYYY-MM-DD): "
echo.
python results_fetcher.py --date %FETCHDATE% --debug
goto END

:END
echo.
pause
