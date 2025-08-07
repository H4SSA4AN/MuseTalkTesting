@echo off
echo MuseTalk Server Launcher
echo =======================
echo.

REM Check if MuseTestEnv exists
conda env list | findstr MuseTestEnv >nul
if errorlevel 1 (
    echo MuseTestEnv environment not found!
    echo Please create the environment first:
    echo conda env create -f environment.yml
    pause
    exit /b 1
)

echo MuseTestEnv environment found.
echo Starting MuseTalk inference server...
echo Server will be available at: http://localhost:8081
echo.
echo Press Ctrl+C to stop the server
echo.

REM Activate MuseTestEnv and run the server
conda activate MuseTestEnv && python musetalkServer/server.py

pause
