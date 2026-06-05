@echo off
REM ============================================================================
REM  AVS Migration Analytics - local launcher for developers (Windows)
REM
REM  Use this if you have Python installed and are running from source.
REM  End users should use the packaged Start_AVS_Analytics.bat instead.
REM
REM  Creates a local .venv on first run, then starts the dashboard.
REM ============================================================================
setlocal
title AVS Migration Analytics (dev)
cd /d "%~dp0"

set "PORT=8501"
set "URL=http://localhost:%PORT%"

where python >nul 2>nul
if errorlevel 1 (
    echo ERROR: Python is not installed or not on PATH.
    echo Install Python 3.10+ from https://www.python.org/downloads/ and retry.
    pause & exit /b 1
)

if not exist ".venv\.deps_installed" (
    echo ==> First run: creating local environment ^(one-time^)...
    python -m venv .venv
    call ".venv\Scripts\activate.bat"
    python -m pip install --quiet --upgrade pip
    python -m pip install --quiet -r requirements.txt
    echo done > ".venv\.deps_installed"
) else (
    call ".venv\Scripts\activate.bat"
)

echo.
echo   Opening %URL% in your browser...
start "" cmd /c "timeout /t 5 /nobreak >nul & start %URL%"

python -m streamlit run Home.py --server.port %PORT% --server.address localhost ^
    --server.headless true --browser.gatherUsageStats false
pause
endlocal
