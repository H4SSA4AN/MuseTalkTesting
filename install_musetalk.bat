@echo off
setlocal enabledelayedexpansion

echo.
echo ============================================================
echo                MuseTalk All-in-One Installation
echo ============================================================
echo.
echo This script will install and configure MuseTalk for you.
echo Make sure you have Anaconda or Miniconda installed.
echo For more information, visit: https://docs.conda.io/en/latest/miniconda.html
echo.

set /p proceed="Do you want to proceed with the installation? (Y/n): "
if /i "%proceed%"=="n" (
    echo Installation cancelled
    pause
    exit /b 0
)

echo.
echo ============================================================
echo                System Requirements Check
echo ============================================================
echo.

REM Check Python version
echo ➤ Checking Python version...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ✗ Python is not installed or not in PATH
    echo Please install Python 3.8+ first
    pause
    exit /b 1
)

for /f "tokens=2" %%i in ('python --version 2^>^&1') do set python_version=%%i
echo ✓ Python %python_version% is compatible

REM Check if conda is installed
echo ➤ Checking if conda is installed...
conda --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ✗ Conda is not installed. Please install Anaconda or Miniconda first.
    echo Download from: https://docs.conda.io/en/latest/miniconda.html
    pause
    exit /b 1
)

for /f "tokens=2" %%i in ('conda --version 2^>^&1') do set conda_version=%%i
echo ✓ Conda is installed (version: %conda_version%)

REM Check if git is installed
echo ➤ Checking if git is installed...
git --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ⚠ Git is not installed. Some features may not work properly.
) else (
    echo ✓ Git is installed
)

echo.
echo ============================================================
echo                Creating Conda Environment
echo ============================================================
echo.

set env_name=MuseTestEnv

REM Check if environment already exists
echo ➤ Checking if MuseTestEnv environment exists...
conda env list | findstr %env_name% >nul
if %errorlevel% equ 0 (
    echo ⚠ Environment 'MuseTestEnv' already exists
    set /p overwrite="Do you want to remove and recreate it? (y/N): "
    if /i "!overwrite!"=="y" (
        echo ➤ Removing existing environment...
        conda env remove -n %env_name% -y
    ) else (
        echo ℹ Using existing environment
        goto :install_deps
    )
)

REM Create environment with Python 3.8
echo ➤ Creating MuseTestEnv environment with Python 3.8...
conda create -n %env_name% python=3.8 -y
if %errorlevel% neq 0 (
    echo ✗ Failed to create conda environment
    pause
    exit /b 1
)

echo ✓ Conda environment created successfully

:install_deps
echo.
echo ============================================================
echo                Installing Dependencies
echo ============================================================
echo.

REM Check if requirements.txt exists
if not exist "requirements.txt" (
    echo ✗ requirements.txt not found in current directory
    pause
    exit /b 1
)

REM Install Python dependencies in the conda environment
echo ➤ Installing Python dependencies...
conda run -n %env_name% pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo ✗ Failed to install Python dependencies
    pause
    exit /b 1
)

echo ✓ Python dependencies installed successfully

REM Check for additional system dependencies
echo ➤ Checking for additional system dependencies...

REM Check for FFmpeg
ffmpeg -version >nul 2>&1
if %errorlevel% neq 0 (
    echo ⚠ FFmpeg not found. You may need to install it manually.
    echo Download from: https://ffmpeg.org/download.html
) else (
    echo ✓ FFmpeg is installed
)

echo.
echo ============================================================
echo                Verifying Installation
echo ============================================================
echo.

REM Test conda environment activation
echo ➤ Testing conda environment activation...
conda run -n %env_name% python -c "import sys; print('Python version:', sys.version)" >nul 2>&1
if %errorlevel% neq 0 (
    echo ✗ Conda environment activation failed
    pause
    exit /b 1
)

echo ✓ Conda environment activation works

REM Test key package imports
echo ➤ Testing key package imports...
for %%p in (torch torchvision numpy opencv-python aiohttp asyncio) do (
    conda run -n %env_name% python -c "import %%p; print('%%p imported successfully')" >nul 2>&1
    if !errorlevel! equ 0 (
        echo ✓ %%p imported successfully
    ) else (
        echo ⚠ %%p import failed
    )
)

echo.
echo ============================================================
echo                Initial Configuration
echo ============================================================
echo.

REM Create .env file if it doesn't exist
if not exist ".env" (
    echo ℹ Creating initial .env file...
    (
        echo # MuseTalk Server Configuration
        echo # Generated by install_musetalk.bat
        echo.
        echo # MuseTalk inference server settings
        echo MUSETALK_HOST=localhost
        echo MUSETALK_PORT=8081
        echo.
        echo # Web interface server settings
        echo WEB_HOST=localhost
        echo WEB_PORT=8080
    ) > .env
    echo ✓ Initial .env file created
) else (
    echo ℹ .env file already exists
)

echo.
echo ============================================================
echo                Installation Complete!
echo ============================================================
echo.
echo ✓ MuseTalk has been successfully installed!
echo.
echo Next steps:
echo 1. Configure your ports (optional): python create_env.py
echo 2. Start the servers: python start_servers.py
echo 3. Open your browser to: http://localhost:8080
echo.
echo For detailed instructions, see: QUICK_START.md
echo.

pause
