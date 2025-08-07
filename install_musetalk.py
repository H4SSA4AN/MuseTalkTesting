#!/usr/bin/env python3
"""
All-in-One MuseTalk Installation Script
This script handles the complete setup of MuseTalk including:
- Conda environment creation
- Dependency installation
- System verification
- Initial configuration
"""

import os
import sys
import subprocess
import platform
import shutil
import time
from pathlib import Path

class Colors:
    """ANSI color codes for terminal output"""
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'

def print_header(text):
    """Print a formatted header"""
    print(f"\n{Colors.HEADER}{Colors.BOLD}{'='*60}")
    print(f"{text:^60}")
    print(f"{'='*60}{Colors.ENDC}\n")

def print_step(text):
    """Print a step message"""
    print(f"{Colors.OKBLUE}➤ {text}{Colors.ENDC}")

def print_success(text):
    """Print a success message"""
    print(f"{Colors.OKGREEN}✓ {text}{Colors.ENDC}")

def print_warning(text):
    """Print a warning message"""
    print(f"{Colors.WARNING}⚠ {text}{Colors.ENDC}")

def print_error(text):
    """Print an error message"""
    print(f"{Colors.FAIL}✗ {text}{Colors.ENDC}")

def print_info(text):
    """Print an info message"""
    print(f"{Colors.OKCYAN}ℹ {text}{Colors.ENDC}")

def check_command_exists(command):
    """Check if a command exists in the system"""
    return shutil.which(command) is not None

def run_command(command, shell=False, capture_output=False, check=True):
    """Run a command and handle errors"""
    try:
        if shell:
            result = subprocess.run(command, shell=True, capture_output=capture_output, text=True, check=check)
        else:
            result = subprocess.run(command, capture_output=capture_output, text=True, check=check)
        return result
    except subprocess.CalledProcessError as e:
        if check:
            print_error(f"Command failed: {' '.join(command) if isinstance(command, list) else command}")
            print_error(f"Error: {e}")
            return None
        return e

def check_system_requirements():
    """Check if the system meets the requirements"""
    print_header("System Requirements Check")
    
    # Check Python version
    print_step("Checking Python version...")
    python_version = sys.version_info
    if python_version.major >= 3 and python_version.minor >= 8:
        print_success(f"Python {python_version.major}.{python_version.minor}.{python_version.micro} is compatible")
    else:
        print_error(f"Python {python_version.major}.{python_version.minor}.{python_version.micro} is not compatible. Python 3.8+ is required.")
        return False
    
    # Check if conda is installed
    print_step("Checking if conda is installed...")
    if check_command_exists("conda"):
        print_success("Conda is installed")
        
        # Get conda version
        result = run_command(["conda", "--version"], capture_output=True)
        if result:
            print_info(f"Conda version: {result.stdout.strip()}")
    else:
        print_error("Conda is not installed. Please install Anaconda or Miniconda first.")
        print_info("Download from: https://docs.conda.io/en/latest/miniconda.html")
        return False
    
    # Check if git is installed
    print_step("Checking if git is installed...")
    if check_command_exists("git"):
        print_success("Git is installed")
    else:
        print_warning("Git is not installed. Some features may not work properly.")
    
    # Check available disk space (at least 10GB recommended)
    print_step("Checking available disk space...")
    try:
        statvfs = os.statvfs('.')
        free_space_gb = (statvfs.f_frsize * statvfs.f_bavail) / (1024**3)
        if free_space_gb >= 10:
            print_success(f"Available disk space: {free_space_gb:.1f} GB")
        else:
            print_warning(f"Available disk space: {free_space_gb:.1f} GB (10+ GB recommended)")
    except:
        print_warning("Could not check disk space")
    
    return True

def create_conda_environment():
    """Create the MuseTalk conda environment"""
    print_header("Creating Conda Environment")
    
    env_name = "MuseTestEnv"
    
    # Check if environment already exists
    print_step("Checking if MuseTestEnv environment exists...")
    result = run_command(["conda", "env", "list"], capture_output=True)
    if result and env_name in result.stdout:
        print_warning(f"Environment '{env_name}' already exists")
        overwrite = input("Do you want to remove and recreate it? (y/N): ").strip().lower()
        if overwrite in ['y', 'yes']:
            print_step("Removing existing environment...")
            run_command(["conda", "env", "remove", "-n", env_name, "-y"])
        else:
            print_info("Using existing environment")
            return True
    
    # Create environment with Python 3.8
    print_step("Creating MuseTestEnv environment with Python 3.8...")
    result = run_command(["conda", "create", "-n", env_name, "python=3.8", "-y"])
    if not result:
        print_error("Failed to create conda environment")
        return False
    
    print_success("Conda environment created successfully")
    return True

def install_dependencies():
    """Install all required dependencies"""
    print_header("Installing Dependencies")
    
    env_name = "MuseTestEnv"
    
    # Check if requirements.txt exists
    if not os.path.exists("requirements.txt"):
        print_error("requirements.txt not found in current directory")
        return False
    
    # Install Python dependencies in the conda environment
    print_step("Installing Python dependencies...")
    
    if platform.system() == "Windows":
        cmd = ["conda", "run", "-n", env_name, "pip", "install", "-r", "requirements.txt"]
    else:
        cmd = ["conda", "run", "-n", env_name, "pip", "install", "-r", "requirements.txt"]
    
    result = run_command(cmd)
    if not result:
        print_error("Failed to install Python dependencies")
        return False
    
    print_success("Python dependencies installed successfully")
    
    # Install additional system dependencies if needed
    print_step("Checking for additional system dependencies...")
    
    # Check for FFmpeg
    if not check_command_exists("ffmpeg"):
        print_warning("FFmpeg not found. You may need to install it manually.")
        print_info("Download from: https://ffmpeg.org/download.html")
    
    # Check for CUDA (optional)
    if platform.system() != "Windows":
        nvidia_smi = run_command(["nvidia-smi"], capture_output=True, check=False)
        if nvidia_smi and nvidia_smi.returncode == 0:
            print_success("NVIDIA GPU detected")
            print_info("CUDA support available")
        else:
            print_info("No NVIDIA GPU detected - will use CPU")
    
    return True

def verify_installation():
    """Verify that the installation was successful"""
    print_header("Verifying Installation")
    
    env_name = "MuseTestEnv"
    
    # Test conda environment activation
    print_step("Testing conda environment activation...")
    if platform.system() == "Windows":
        test_cmd = ["conda", "run", "-n", env_name, "python", "-c", "import sys; print('Python version:', sys.version)"]
    else:
        test_cmd = ["conda", "run", "-n", env_name, "python", "-c", "import sys; print('Python version:', sys.version)"]
    
    result = run_command(test_cmd, capture_output=True)
    if result:
        print_success("Conda environment activation works")
        print_info(result.stdout.strip())
    else:
        print_error("Conda environment activation failed")
        return False
    
    # Test key package imports
    print_step("Testing key package imports...")
    test_imports = [
        "torch",
        "torchvision", 
        "numpy",
        "opencv-python",
        "aiohttp",
        "asyncio"
    ]
    
    for package in test_imports:
        try:
            if platform.system() == "Windows":
                cmd = ["conda", "run", "-n", env_name, "python", "-c", f"import {package}; print('{package} imported successfully')"]
            else:
                cmd = ["conda", "run", "-n", env_name, "python", "-c", f"import {package}; print('{package} imported successfully')"]
            
            result = run_command(cmd, capture_output=True)
            if result:
                print_success(f"{package} imported successfully")
            else:
                print_warning(f"{package} import failed")
        except Exception as e:
            print_warning(f"{package} import failed: {e}")
    
    return True

def setup_initial_configuration():
    """Set up initial configuration"""
    print_header("Initial Configuration")
    
    print_step("Setting up environment configuration...")
    
    # Create .env file if it doesn't exist
    if not os.path.exists(".env"):
        print_info("Creating initial .env file...")
        env_content = """# MuseTalk Server Configuration
# Generated by install_musetalk.py

# MuseTalk inference server settings
MUSETALK_HOST=localhost
MUSETALK_PORT=8081

# Web interface server settings
WEB_HOST=localhost
WEB_PORT=8080
"""
        try:
            with open(".env", "w") as f:
                f.write(env_content)
            print_success("Initial .env file created")
        except Exception as e:
            print_error(f"Failed to create .env file: {e}")
    else:
        print_info(".env file already exists")
    
    # Make shell scripts executable on Unix systems
    if platform.system() != "Windows":
        print_step("Making shell scripts executable...")
        scripts = ["start_servers.sh"]
        for script in scripts:
            if os.path.exists(script):
                try:
                    os.chmod(script, 0o755)
                    print_success(f"Made {script} executable")
                except Exception as e:
                    print_warning(f"Could not make {script} executable: {e}")

def create_quick_start_guide():
    """Create a quick start guide"""
    print_header("Quick Start Guide")
    
    guide_content = """# MuseTalk Quick Start Guide

## Getting Started

1. **Configure Ports (Optional)**
   ```bash
   python create_env.py
   ```
   This will help you set custom port numbers if needed.

2. **Start the Servers**
   ```bash
   # Option 1: Python script (recommended)
   python start_servers.py
   
   # Option 2: Shell script (Linux/Mac)
   ./start_servers.sh
   
   # Option 3: Batch script (Windows)
   start_servers.bat
   ```

3. **Access the Web Interface**
   - Open your web browser
   - Navigate to: http://localhost:8080
   - The MuseTalk interface should load

## Troubleshooting

- **Port already in use**: Run `python create_env.py` to change ports
- **Environment issues**: Make sure to activate the MuseTestEnv conda environment
- **Dependencies missing**: Re-run the installation script

## Useful Commands

- **Debug server state**: `python debug_state.py`
- **Test settings API**: `python test_settings_api.py`
- **Test inference restart**: `python test_inference_restart.py`

## Support

For more information, see:
- ENVIRONMENT_SETUP.md - Environment configuration details
- README.md - General project information
"""
    
    try:
        with open("QUICK_START.md", "w") as f:
            f.write(guide_content)
        print_success("Quick start guide created (QUICK_START.md)")
    except Exception as e:
        print_error(f"Failed to create quick start guide: {e}")

def main():
    """Main installation function"""
    print_header("MuseTalk All-in-One Installation")
    
    print_info("This script will install and configure MuseTalk for you.")
    print_info("Make sure you have Anaconda or Miniconda installed.")
    print_info("For more information, visit: https://docs.conda.io/en/latest/miniconda.html")
    
    # Ask for confirmation
    proceed = input("\nDo you want to proceed with the installation? (Y/n): ").strip().lower()
    if proceed in ['n', 'no']:
        print_info("Installation cancelled")
        return
    
    # Check system requirements
    if not check_system_requirements():
        print_error("System requirements not met. Please fix the issues above and try again.")
        return
    
    # Create conda environment
    if not create_conda_environment():
        print_error("Failed to create conda environment")
        return
    
    # Install dependencies
    if not install_dependencies():
        print_error("Failed to install dependencies")
        return
    
    # Verify installation
    if not verify_installation():
        print_warning("Installation verification failed. Some components may not work properly.")
    
    # Setup initial configuration
    setup_initial_configuration()
    
    # Create quick start guide
    create_quick_start_guide()
    
    # Final success message
    print_header("Installation Complete!")
    print_success("MuseTalk has been successfully installed!")
    print_info("Next steps:")
    print_info("1. Configure your ports (optional): python create_env.py")
    print_info("2. Start the servers: python start_servers.py")
    print_info("3. Open your browser to: http://localhost:8080")
    print_info("\nFor detailed instructions, see: QUICK_START.md")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nInstallation interrupted by user")
        sys.exit(1)
    except Exception as e:
        print_error(f"Unexpected error: {e}")
        sys.exit(1)
