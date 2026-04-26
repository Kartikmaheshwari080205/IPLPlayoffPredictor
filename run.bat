@echo off
setlocal

if /i "%~1"=="-t" goto run_temp
if /i "%~1"=="-p" goto run_predictor
if /i "%~1"=="-h" goto help
if /i "%~1"=="--help" goto help

python refresh_ipl_data.py %*
exit /b %errorlevel%

:run_temp
python refresh_ipl_data.py
temp.exe %2 %3 %4 %5 %6 %7 %8 %9
exit /b %errorlevel%

:run_predictor
python refresh_ipl_data.py
predictor.exe %2 %3 %4 %5 %6 %7 %8 %9
exit /b %errorlevel%

:help
echo Usage:
echo   run.bat           Run refresh_ipl_data.py
echo   run.bat -t        Run temp.exe
echo   run.bat -p        Run predictor.exe
exit /b 0
