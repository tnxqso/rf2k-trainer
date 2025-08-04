@echo off
title RF2K Trainer Launcher
cd /d "%USERPROFILE%\rf2k-trainer"

:menu
cls
echo ========================================
echo         RF2K-TRAINER LAUNCH MENU        
echo ========================================
echo.
echo 1. Run full tuning (all enabled bands)
echo 2. Show tuning info (segments per band)
echo 3. Tune specific band(s)
echo 4. Run in debug mode
echo 5. Clear old logs
echo 0. Exit
echo.
set /p choice=Choose an option [0-5]: 

if "%choice%"=="1" goto full
if "%choice%"=="2" goto info
if "%choice%"=="3" goto band
if "%choice%"=="4" goto debug
if "%choice%"=="5" goto clear
if "%choice%"=="0" exit
goto menu

:full
python main.py
goto end

:info
python main.py info
goto end

:band
set /p bands=Enter band(s) (e.g. 60 80 160): 
python main.py %bands%
goto end

:debug
python main.py --debug
goto end

:clear
python main.py --clear-logs
goto end

:end
echo.
echo Done. Press any key to return to menu...
pause >nul
goto menu
