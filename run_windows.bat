@echo off
REM Starts the channel tuner. First run creates a virtual environment and
REM installs Flask and requests into it; later runs just start the server.
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo Setting up Python environment, one moment...
    python -m venv .venv || goto :nopython
    ".venv\Scripts\python.exe" -m pip install --upgrade pip >nul
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt || goto :nodeps
)

".venv\Scripts\python.exe" app.py %*
goto :eof

:nopython
echo.
echo Python was not found. Install Python 3.10 or newer and tick
echo "Add python.exe to PATH" during setup, then run this file again.
pause
goto :eof

:nodeps
echo.
echo Could not install Flask and requests. Check your internet connection.
pause
