@echo off
cd /d "%~dp0"
echo Installing/checking dependencies...
pip install customtkinter pandas requests openpyxl 2>nul
if %ERRORLEVEL% NEQ 0 (
    py -m pip install customtkinter pandas requests openpyxl 2>nul
)
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo Could not install packages automatically.
    echo Open a terminal in this folder and run:
    echo   pip install customtkinter pandas requests openpyxl
    echo.
    pause
    exit /b 1
)
echo Starting Terrascope Lead Finder...
python main.py
if %ERRORLEVEL% NEQ 0 (
    py main.py
)
pause
