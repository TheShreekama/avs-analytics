@echo off
REM ============================================================================
REM  AVS Migration Analytics - Launcher
REM
REM  Double-click this file to start the application. It launches a fully local
REM  web app and opens your browser at http://localhost:8501.
REM
REM  Nothing is installed on your machine and no data ever leaves it.
REM  In the packaged ZIP, a private Python runtime lives in the .\runtime folder,
REM  so you do NOT need Python (or anything else) installed.
REM ============================================================================
setlocal
title AVS Migration Analytics
cd /d "%~dp0"

set "PORT=8501"
set "URL=http://localhost:%PORT%"

REM --- 1) Locate a Python interpreter -----------------------------------------
REM Prefer the bundled private runtime; fall back to a system Python for devs.
set "PYEXE="
if exist "%~dp0runtime\python.exe" set "PYEXE=%~dp0runtime\python.exe"
if not defined PYEXE if exist "%~dp0runtime\Scripts\python.exe" set "PYEXE=%~dp0runtime\Scripts\python.exe"
if not defined PYEXE (
    where py >nul 2>nul && set "PYEXE=py"
)
if not defined PYEXE (
    where python >nul 2>nul && set "PYEXE=python"
)
if not defined PYEXE (
    echo.
    echo  [ERROR] No bundled runtime found and Python is not installed.
    echo  If you downloaded the source ^(not the packaged ZIP^), run:
    echo        build_windows.ps1   to create the portable bundle, or
    echo        run_local.bat       to run with your own Python.
    echo.
    pause
    exit /b 1
)

echo.
echo   ============================================================
echo     AVS Migration Analytics
echo     Starting local dashboard ... please wait.
echo     A browser window will open at %URL%
echo     (Keep this window open while using the app. Close it to quit.)
echo   ============================================================
echo.

REM --- 2) Open the browser shortly after the server starts --------------------
start "" cmd /c "timeout /t 5 /nobreak >nul & start %URL%"

REM --- 3) Run the app (foreground; closing this window stops the server) -------
"%PYEXE%" -m streamlit run "%~dp0Home.py" ^
    --server.port %PORT% ^
    --server.address localhost ^
    --server.headless true ^
    --browser.gatherUsageStats false ^
    --global.developmentMode false

echo.
echo  The application has stopped.
pause
endlocal
