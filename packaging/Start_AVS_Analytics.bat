@echo off
REM ============================================================================
REM  AVS Migration Analytics - Launcher
REM
REM  Double-click this file to start the application. It launches a fully local
REM  web app and opens your browser at http://127.0.0.1:8501
REM
REM  Nothing is installed on your machine and no data ever leaves it.
REM  In the packaged ZIP, a private Python runtime lives in the .\runtime folder,
REM  so you do NOT need Python (or anything else) installed.
REM
REM  NOTE: we use http:// and the 127.0.0.1 IP form on purpose. Many corporate
REM  browsers force "localhost" to HTTPS, which a local app cannot serve. A bare
REM  IP address is never upgraded, so the app loads reliably.
REM ============================================================================
setlocal EnableExtensions
title AVS Migration Analytics
cd /d "%~dp0"

set "PORT=8501"
set "HOSTIP=127.0.0.1"
set "URL=http://%HOSTIP%:%PORT%"

REM --- 1) Locate a Python interpreter -----------------------------------------
REM Prefer the bundled private runtime; fall back to a system Python for devs.
set "PYEXE="
if exist "%~dp0runtime\python.exe" set "PYEXE=%~dp0runtime\python.exe"
if not defined PYEXE if exist "%~dp0runtime\Scripts\python.exe" set "PYEXE=%~dp0runtime\Scripts\python.exe"
if not defined PYEXE where py >nul 2>nul && set "PYEXE=py"
if not defined PYEXE where python >nul 2>nul && set "PYEXE=python"
if not defined PYEXE goto NOPY

echo.
echo   ============================================================
echo     AVS Migration Analytics is starting... please wait.
echo.
echo     Your browser should open automatically in a few seconds.
echo     If it does not, open this address manually:
echo.
echo            %URL%
echo.
echo     IMPORTANT: use http and 127.0.0.1  (NOT https, NOT localhost)
echo     Keep THIS window open while using the app. Close it to quit.
echo   ============================================================
echo.

REM --- 2) Open the browser only AFTER the server answers ----------------------
where curl.exe >nul 2>nul
if errorlevel 1 (
    start "" /min cmd /c "timeout /t 12 /nobreak >nul & start %URL%"
) else (
    start "" /min cmd /c "curl.exe -fs -o nul --retry 60 --retry-delay 1 --retry-connrefused %URL%/_stcore/health & start %URL%"
)

REM --- 3) Run the app (foreground; closing this window stops the server) -------
"%PYEXE%" -m streamlit run "%~dp0Home.py" --server.port %PORT% --server.address %HOSTIP% --server.headless true --browser.serverAddress %HOSTIP% --browser.gatherUsageStats false --global.developmentMode false

echo.
echo  The application has stopped.
pause
goto END

:NOPY
echo.
echo  [ERROR] No bundled runtime found and Python is not installed.
echo  If you downloaded the source (not the packaged ZIP), run:
echo        build_windows.ps1   to create the portable bundle, or
echo        run_local.bat       to run with your own Python.
echo.
pause
goto END

:END
endlocal
