@echo off
setlocal EnableExtensions
title RF2K Trainer Launcher

rem Always run from the folder where this .bat resides
set "LAUNCHER_DIR=%~dp0"
cd /d "%LAUNCHER_DIR%"

rem Recommended install folder for reference/warning
set "RECOMM=%USERPROFILE%\rf2k-trainer\"

rem Warn if launcher is not in the recommended folder (no directory change)
if /I not "%LAUNCHER_DIR%"=="%RECOMM%" (
  echo [WARNING] You are launching from:
  echo           "%LAUNCHER_DIR%"
  echo           Recommended install folder:
  echo           "%RECOMM%"
  echo.
  echo This is fine if intentional.
  echo.
  echo Press any key to continue...
  pause >nul
)

rem ---- Ensure first-run setup (settings.yml + logs\) ----
call :ensure_setup || goto endall

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
if "%choice%"=="0" goto endall
goto menu

:full
call :run_cmd
goto post_run

:info
call :run_cmd --info
goto post_run

:band
set /p bands=Enter band(s) (e.g. 60 80 160): 
call :run_cmd %bands%
goto post_run

:debug
set /p bands=Enter band(s) for debug (or leave blank for all): 
if "%bands%"=="" (
  call :run_cmd --debug
) else (
  call :run_cmd --debug %bands%
)
goto post_run

:clear
call :run_cmd --clear-logs
goto post_run

:run_cmd
rem Prefer EXE next to the .bat; then EXE in recommended folder; else Python.
set "RC="
if exist ".\rf2k-trainer.exe" (
  ".\rf2k-trainer.exe" %*
) else if exist "%RECOMM%rf2k-trainer.exe" (
  "%RECOMM%rf2k-trainer.exe" %*
) else (
  python main.py %*
)
set "RC=%ERRORLEVEL%"
exit /b %RC%

:post_run
echo.
if not "%RC%"=="0" (
  echo The trainer exited with code %RC%.
)
echo Press any key to return to menu...
pause >nul
goto menu

:ensure_setup
rem Create logs folder if missing
if not exist ".\logs" mkdir ".\logs"

rem Create settings.yml if missing (copy example if present, else write minimal safe default)
if not exist ".\settings.yml" (
  if exist ".\settings.example.yml" (
    copy /y ".\settings.example.yml" ".\settings.yml" >nul
    set "NEWCFG=1"
  ) else (
    set "NEWCFG=1"
    (
      echo defaults:
      echo   iaru_region: 1
      echo   drive_power: 13
      echo   use_beep: true
      echo   auto_set_cw_mode: true
      echo   restore_state: true
      echo rf2k_s:
      echo   enabled: false
      echo   host: 127.0.0.1
      echo   port: 8080
      echo radio:
      echo   type: flex
      echo   host: 127.0.0.1
      echo   port: 4992
      echo bands: {}
    ) > ".\settings.yml"
  )
)

rem Offer to open newly created config
if defined NEWCFG (
  echo.
  echo A new settings.yml has been created here:
  echo   "%LAUNCHER_DIR%settings.yml"
  echo.
  set "ans=Y"
  set /p ans=Open it in Notepad now? [Y/n]: 
  if /I not "%ans%"=="N" start "" notepad ".\settings.yml"
  echo.
  echo When done editing, save and close Notepad, then press any key...
  pause >nul
)
exit /b 0

:endall
endlocal
exit /b 0
