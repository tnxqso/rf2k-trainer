@echo off
setlocal EnableExtensions
title RF2K Trainer Launcher

rem Always run from the folder where this .bat resides
set "LAUNCHER_DIR=%~dp0"
cd /d "%LAUNCHER_DIR%"

rem --- Choose state directory: prefer local folder; fallback to LocalAppData if not writable ---
set "STATE_DIR=%LAUNCHER_DIR%"
copy /y nul "%STATE_DIR%.__writetest__" >nul 2>&1
if errorlevel 1 (
  set "STATE_DIR=%LOCALAPPDATA%\RF2K-TRAINER\"
  if not exist "%STATE_DIR%" mkdir "%STATE_DIR%" >nul 2>&1
) else (
  del /q "%STATE_DIR%.__writetest__" >nul 2>&1
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
echo 6. Check for updates
echo 0. Exit
echo.
set /p choice=Choose an option [0-6]: 

if "%choice%"=="1" goto full
if "%choice%"=="2" goto info
if "%choice%"=="3" goto band
if "%choice%"=="4" goto debug
if "%choice%"=="5" goto clear
if "%choice%"=="6" goto updates
if "%choice%"=="0" goto endall
goto menu

:full
call :run_cmd
set "RC=%ERRORLEVEL%"
goto post_run

:info
call :run_cmd --info
set "RC=%ERRORLEVEL%"
goto post_run

:band
set /p bands=Enter band(s) (e.g. 60 80 160):
call :run_cmd %bands%
set "RC=%ERRORLEVEL%"
goto post_run

:debug
set /p bands=Enter band(s) for debug (or leave blank for all):
if "%bands%"=="" (
  call :run_cmd --debug
) else (
  call :run_cmd --debug %bands%
)
set "RC=%ERRORLEVEL%"
goto post_run

:clear
call :run_cmd --clear-logs
set "RC=%ERRORLEVEL%"
goto post_run

:updates
call :run_cmd --check-updates
set "RC=%ERRORLEVEL%"
goto post_run

:run_cmd
rem Prefer EXE next to the .bat; else Python from source. Always use STATE_DIR as working dir.
if exist ".\rf2k-trainer.exe" (
  pushd "%STATE_DIR%"
  "%LAUNCHER_DIR%rf2k-trainer.exe" %*
  set "RC=%ERRORLEVEL%"
  popd
) else (
  pushd "%STATE_DIR%"
  python "%LAUNCHER_DIR%main.py" %*
  set "RC=%ERRORLEVEL%"
  popd
)
exit /b %RC%

:post_run
echo.

rem Close if updater created the sentinel flag (works even if ERRORLEVEL got reset).
if exist "%STATE_DIR%rf2k-update.flag" (
  del /q "%STATE_DIR%rf2k-update.flag" >nul 2>&1
  echo Update installer has been started.
  echo Log: %TEMP%\RF2K-TRAINER_update.log
  echo.
  echo Press any key to exit this launcher...
  pause >nul
  goto endall
)

rem If updater propagated exit code 111, also close.
if "%RC%"=="111" goto endall

if not "%RC%"=="0" (
  echo The trainer exited with code %RC%.
)
echo Press any key to return to menu...
pause >nul
goto menu


:ensure_setup
rem Create logs folder if missing (in chosen STATE_DIR)
if not exist "%STATE_DIR%logs" mkdir "%STATE_DIR%logs" >nul 2>&1

rem Create settings.yml if missing (copy example if present)
if not exist "%STATE_DIR%settings.yml" (
  if exist "%LAUNCHER_DIR%settings.example.yml" (
    copy /y "%LAUNCHER_DIR%settings.example.yml" "%STATE_DIR%settings.yml" >nul
    set "NEWCFG=1"
  )
)

rem Offer to open newly created config
if defined NEWCFG (
  echo.
  echo A new settings.yml has been created here:
  echo   "%STATE_DIR%settings.yml"
  echo.
  set "ans=Y"
  set /p ans=Open it in Notepad now? [Y/n]:
  if /I not "%ans%"=="N" start "" notepad "%STATE_DIR%settings.yml"
  echo.
  echo When done editing, save and close Notepad, then press any key...
  pause >nul
)
exit /b 0

:endall
endlocal
exit /b 0
