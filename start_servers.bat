@echo off
echo Starting MuseTalk with separated servers...
echo.
echo MuseTalk inference server will run on port 8081 (in MuseTestEnv)
echo Web interface server will run on port 8080
echo.
echo Press Ctrl+C to stop both servers
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

echo MuseTestEnv environment found. Starting servers...
echo.

REM Start MuseTalk server in MuseTestEnv environment
start "MuseTalk Server" cmd /c "conda activate MuseTestEnv && python musetalkServer/server.py"

REM Wait for MuseTalk server to initialize
echo Waiting for MuseTalk server to initialize...
timeout /t 5 /nobreak >nul

REM Start web server
echo Starting web interface server...
python webrtc/server.py

pause
