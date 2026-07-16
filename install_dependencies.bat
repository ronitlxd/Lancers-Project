@echo off
echo Installing missing Python dependencies for LancersPulse...
echo.

set VENV_PIP="%~dp0.venv\Scripts\pip.exe"

if not exist %VENV_PIP% (
    echo ERROR: Virtual environment not found at .venv\Scripts\pip.exe
    echo Please activate your virtual environment and run: pip install openpyxl reportlab
    pause
    exit /b 1
)

%VENV_PIP% install openpyxl reportlab
echo.
echo Done! Restart the Django server for changes to take effect.
pause
