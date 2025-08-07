# MuseTalk Installation Guide

This guide provides comprehensive instructions for installing MuseTalk using the all-in-one installation scripts.

## Prerequisites

Before running the installation, ensure you have the following:

### Required Software
- **Python 3.8 or higher** - [Download Python](https://www.python.org/downloads/)
- **Anaconda or Miniconda** - [Download Miniconda](https://docs.conda.io/en/latest/miniconda.html)
- **Git** (optional but recommended) - [Download Git](https://git-scm.com/downloads)

### System Requirements
- **Operating System**: Windows 10+, macOS 10.14+, or Linux (Ubuntu 18.04+)
- **RAM**: Minimum 8GB, Recommended 16GB+
- **Storage**: At least 10GB free space
- **GPU**: Optional but recommended for better performance (NVIDIA GPU with CUDA support)

## Installation Options

### Option 1: All-in-One Installation (Recommended)

Choose the appropriate script for your operating system:

#### Windows
```bash
# Run the Windows batch installer
install_musetalk.bat
```

#### Linux/macOS
```bash
# Make the script executable and run
chmod +x install_musetalk.sh
./install_musetalk.sh
```

#### Cross-Platform (Python)
```bash
# Run the Python installer (works on all platforms)
python install_musetalk.py
```

### Option 2: Manual Installation

If you prefer to install manually or the automated scripts don't work:

1. **Create Conda Environment**
   ```bash
   conda create -n MuseTestEnv python=3.8 -y
   ```

2. **Activate Environment**
   ```bash
   conda activate MuseTestEnv
   ```

3. **Install Dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Create Configuration**
   ```bash
   python create_env.py
   ```

## What the Installation Scripts Do

The all-in-one installation scripts perform the following steps:

### 1. System Requirements Check
- ✅ Verifies Python version (3.8+)
- ✅ Checks if conda is installed
- ✅ Validates git installation
- ✅ Checks available disk space
- ✅ Detects NVIDIA GPU (optional)

### 2. Conda Environment Setup
- ✅ Creates `MuseTestEnv` environment with Python 3.8
- ✅ Handles existing environment conflicts
- ✅ Provides option to recreate environment if needed

### 3. Dependency Installation
- ✅ Installs all Python packages from `requirements.txt`
- ✅ Checks for system dependencies (FFmpeg, CUDA)
- ✅ Provides guidance for missing dependencies

### 4. Installation Verification
- ✅ Tests conda environment activation
- ✅ Verifies key package imports
- ✅ Validates system configuration

### 5. Initial Configuration
- ✅ Creates default `.env` file with port settings
- ✅ Sets up environment variables
- ✅ Makes shell scripts executable (Unix systems)

### 6. Documentation
- ✅ Generates `QUICK_START.md` guide
- ✅ Provides next steps instructions

## Post-Installation Setup

After successful installation, follow these steps:

### 1. Configure Ports (Optional)
If you need to use different ports (e.g., if 8080/8081 are already in use):

```bash
python create_env.py
```

This interactive script will help you:
- Set custom port numbers
- Enable remote access (if needed)
- Configure host bindings

### 2. Start the Servers

Choose your preferred method:

```bash
# Python script (recommended)
python start_servers.py

# Shell script (Linux/macOS)
./start_servers.sh

# Batch script (Windows)
start_servers.bat
```

### 3. Access the Web Interface
- Open your web browser
- Navigate to: `http://localhost:8080` (or your custom port)
- The MuseTalk interface should load

## Troubleshooting

### Common Issues

#### 1. Conda Not Found
**Error**: `conda: command not found`

**Solution**:
- Install Anaconda or Miniconda
- Add conda to your PATH
- Restart your terminal/command prompt

#### 2. Python Version Issues
**Error**: `Python version not compatible`

**Solution**:
- Install Python 3.8 or higher
- Ensure Python is in your PATH
- Use `python --version` to verify

#### 3. Port Already in Use
**Error**: `Address already in use`

**Solution**:
```bash
# Change ports using the configuration script
python create_env.py

# Or manually edit .env file
# MUSETALK_PORT=8082
# WEB_PORT=8083
```

#### 4. Dependencies Installation Failed
**Error**: `Failed to install Python dependencies`

**Solution**:
- Check internet connection
- Try updating pip: `pip install --upgrade pip`
- Install dependencies manually: `pip install -r requirements.txt`
- Check for conflicting packages

#### 5. FFmpeg Not Found
**Warning**: `FFmpeg not found`

**Solution**:
- **Windows**: Download from [FFmpeg.org](https://ffmpeg.org/download.html)
- **macOS**: `brew install ffmpeg`
- **Ubuntu/Debian**: `sudo apt install ffmpeg`
- **CentOS/RHEL**: `sudo yum install ffmpeg`

#### 6. CUDA Issues
**Warning**: `CUDA not available`

**Solution**:
- Install NVIDIA drivers
- Install CUDA Toolkit
- Install cuDNN
- Verify with `nvidia-smi`

### Environment-Specific Issues

#### Windows
- **PowerShell Execution Policy**: Run `Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser`
- **Path Issues**: Ensure Python and conda are in your system PATH
- **Antivirus**: Temporarily disable antivirus if installation fails

#### macOS
- **Homebrew**: Install using `brew install python conda`
- **Permissions**: Use `sudo` if needed for system-wide installation
- **M1 Macs**: Use Rosetta 2 for x86 packages if needed

#### Linux
- **Package Manager**: Update system packages first
- **Dependencies**: Install system dependencies: `sudo apt install build-essential`
- **Permissions**: Ensure proper file permissions

## Verification Commands

After installation, verify everything works:

```bash
# Test conda environment
conda activate MuseTestEnv
python --version

# Test key packages
python -c "import torch; print('PyTorch:', torch.__version__)"
python -c "import cv2; print('OpenCV:', cv2.__version__)"

# Test server startup
python start_servers.py
```

## Support and Resources

### Documentation
- **Quick Start**: `QUICK_START.md`
- **Environment Setup**: `ENVIRONMENT_SETUP.md`
- **Main README**: `README.md`

### Testing Scripts
- **Debug Server State**: `python debug_state.py`
- **Test Settings API**: `python test_settings_api.py`
- **Test Inference Restart**: `python test_inference_restart.py`

### Getting Help
1. Check the troubleshooting section above
2. Review the generated `QUICK_START.md`
3. Check system requirements
4. Verify conda environment activation
5. Test individual components

## Advanced Configuration

### Custom Environment Variables
You can set additional environment variables in your `.env` file:

```bash
# Performance tuning
CUDA_VISIBLE_DEVICES=0
OMP_NUM_THREADS=4

# Debugging
PYTHONPATH=./musetalk
LOG_LEVEL=DEBUG
```

### Remote Access Setup
To enable access from other machines:

```bash
# Edit .env file
MUSETALK_HOST=0.0.0.0
WEB_HOST=0.0.0.0

# Configure firewall
# Ubuntu/Debian
sudo ufw allow 8080
sudo ufw allow 8081

# CentOS/RHEL
sudo firewall-cmd --permanent --add-port=8080/tcp
sudo firewall-cmd --permanent --add-port=8081/tcp
sudo firewall-cmd --reload
```

## Uninstallation

To completely remove MuseTalk:

```bash
# Remove conda environment
conda env remove -n MuseTestEnv

# Remove configuration files
rm -f .env
rm -f QUICK_START.md

# Remove downloaded models (if any)
rm -rf models/
```

## Next Steps

After successful installation:

1. **Read the Quick Start Guide**: `QUICK_START.md`
2. **Configure your environment**: `python create_env.py`
3. **Start the servers**: `python start_servers.py`
4. **Access the web interface**: Open your browser
5. **Test the system**: Run inference tests
6. **Customize settings**: Adjust FPS, batch size, etc.

Congratulations! You've successfully installed MuseTalk and are ready to start using it.
