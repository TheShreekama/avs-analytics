@echo off
REM ============================================================================
REM  AVS Migration Analytics - local launcher for developers (Windows)
REM
REM  Use this if you have Python installed and are running from source.
REM  Creates a local .venv on first run, then starts the dashboard and opens
REM  your browser at http://127.0.0.1:8501
REM
REM  NOTE: we use http:// and the 127.0.0.1 IP form on purpose. Many corporate
REM  browsers force "localhost" to HTTPS, which a local app cannot serve. A bare
REM  IP address is never upgraded, so the app loads reliably.
REM ============================================================================
setlocal EnableExtensions
title AVS Migration Analytics (dev)
cd /d "%~dp0"

set "PORT=8501"
set "HOSTIP=127.0.0.1"
set "URL=http://%HOSTIP%:%PORT%"

where python >nul 2>nul
if errorlevel 1 goto NOPY

if exist ".venv\.deps_installed" goto RUN

echo ==^> First run: creating a local environment and installing packages.
echo     This one-time step can take a few minutes (longer if antivirus
echo     scans each file). Please wait and watch for any errors below...
echo.
python -m venv .venv
if errorlevel 1 goto VENVFAIL
call ".venv\Scripts\activate.bat"
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
if errorlevel 1 goto PIPFAIL
echo done > ".venv\.deps_installed"
goto RUN

:RUN
call ".venv\Scripts\activate.bat"
echo.
echo   ============================================================
echo     AVS Migration Analytics is starting...
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

REM Open the browser only AFTER the local server answers, using the built-in
REM curl.exe to poll the health endpoint (falls back to a fixed wait if absent).
where curl.exe >nul 2>nul
if errorlevel 1 (
    start "" /min cmd /c "timeout /t 12 /nobreak >nul & start %URL%"
) else (
    start "" /min cmd /c "curl.exe -fs -o nul --retry 60 --retry-delay 1 --retry-connrefused %URL%/_stcore/health & start %URL%"
)

python -m streamlit run Home.py --server.port %PORT% --server.address %HOSTIP% --server.headless true --browser.serverAddress %HOSTIP% --browser.gatherUsageStats false

echo.
echo  The application has stopped.
pause
goto END

:NOPY
echo.
echo  [ERROR] Python is not installed or not on PATH.
echo  Install Python 3.11 from https://www.python.org/downloads/
echo  (tick "Add Python to PATH" during setup), then re-run this file.
echo.
pause
goto END

:VENVFAIL
echo.
echo  [ERROR] Could not create the virtual environment (.venv).
echo  Make sure you have write permission in this folder, then retry.
echo.
pause
goto END

:PIPFAIL
echo.
echo  [ERROR] Package installation failed.
echo  If you are behind a corporate proxy, set it and run this file again:
echo        set HTTPS_PROXY=http://your-proxy:port
echo        set HTTP_PROXY=http://your-proxy:port
echo  (Ask your IT helpdesk for the proxy address.)
echo.
pause
goto END

:END
endlocal
