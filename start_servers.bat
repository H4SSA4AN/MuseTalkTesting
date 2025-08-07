@echo off
echo Starting MuseTalk with separated servers...
echo.

REM Load environment variables from .env file if it exists
if exist .env (
    echo Loading environment variables from .env file...
    for /f "tokens=1,2 delims==" %%a in (.env) do (
        if not "%%a"=="" if not "%%a:~0,1%"=="#" (
            set "%%a=%%b"
        )
    )
    echo Environment variables loaded successfully
) else (
    echo No .env file found, using default configuration
)

REM Get port numbers from environment or use defaults
set MUSETALK_PORT=%MUSETALK_PORT%
if "%MUSETALK_PORT%"=="" set MUSETALK_PORT=8081

set WEB_PORT=%WEB_PORT%
if "%WEB_PORT%"=="" set WEB_PORT=8080

set MUSETALK_HOST=%MUSETALK_HOST%
if "%MUSETALK_HOST%"=="" set MUSETALK_HOST=localhost

set WEB_HOST=%WEB_HOST%
if "%WEB_HOST%"=="" set WEB_HOST=localhost

echo MuseTalk inference server will run on %MUSETALK_HOST%:%MUSETALK_PORT% (in MuseTestEnv)
echo Web interface server will run on %WEB_HOST%:%WEB_PORT%
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
