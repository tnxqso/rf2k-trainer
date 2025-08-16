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

rem --- Single-instance guard (PID lock) ---
set "LOCK=%STATE_DIR%rf2k-trainer.launch.lock"

if exist "%LOCK%" (
  rem If lock exists, check if the recorded PID is still alive
  for /f "usebackq delims=" %%E in (`powershell -NoProfile -Command ^
    "try { $pidTxt = Get-Content -LiteralPath '%LOCK%' -Raw; if([string]::IsNullOrWhiteSpace($pidTxt)){ exit 0 } ;" ^
    "try { Get-Process -Id ([int]$pidTxt) -ErrorAction Stop | Out-Null; exit 99 } catch { exit 0 } } catch { exit 0 }"`) do set "DUMMY=%%E"
  if errorlevel 99 (
    echo [INFO] RF2K-TRAINER Launcher is already running.
    echo        If this is unexpected, close the other window or delete:
    echo        "%LOCK%"
    timeout /t 5 >nul
    exit /b 1
  ) else (
    rem Stale or empty lock -> remove it
    del /q "%LOCK%" 2>nul
  )
)

rem Write our own PID to the lock file
for /f %%P in ('powershell -NoProfile -Command "$PID"') do set "SELF_PID=%%P"
> "%LOCK%" echo %SELF_PID%

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
rem Prefer EXE next to the .bat; else Python from source. Always use STATE_DIR as working dir.
set "RC="
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
if not "%RC%"=="0" (
  echo The trainer exited with code %RC%.
)
echo Press any key to return to menu...
pause >nul
goto menu

:ensure_setup
rem Create logs folder if missing (in chosen STATE_DIR)
if not exist "%STATE_DIR%logs" mkdir "%STATE_DIR%logs" >nul 2>&1

rem Create settings.yml if missing (copy example if present, else write minimal safe default)
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
rem Clean up the lock on normal exit
if exist "%LOCK%" del /q "%LOCK%" 2>nul
endlocal
exit /b 0
