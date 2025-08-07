#!/bin/bash

# Colors for terminal output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
PURPLE='\033[0;35m'
NC='\033[0m' # No Color
BOLD='\033[1m'

# Function to print headers
print_header() {
    echo -e "\n${PURPLE}${BOLD}============================================================"
    echo -e "$1"
    echo -e "============================================================${NC}\n"
}

# Function to print step messages
print_step() {
    echo -e "${BLUE}➤ $1${NC}"
}

# Function to print success messages
print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

# Function to print warning messages
print_warning() {
    echo -e "${YELLOW}⚠ $1${NC}"
}

# Function to print error messages
print_error() {
    echo -e "${RED}✗ $1${NC}"
}

# Function to print info messages
print_info() {
    echo -e "${CYAN}ℹ $1${NC}"
}

# Function to check if command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Function to run command and handle errors
run_command() {
    if "$@"; then
        return 0
    else
        print_error "Command failed: $*"
        return 1
    fi
}

# Function to check system requirements
check_system_requirements() {
    print_header "System Requirements Check"
    
    # Check Python version
    print_step "Checking Python version..."
    if command_exists python3; then
        python_version=$(python3 --version 2>&1 | cut -d' ' -f2)
        python_major=$(echo $python_version | cut -d'.' -f1)
        python_minor=$(echo $python_version | cut -d'.' -f2)
        
        if [ "$python_major" -ge 3 ] && [ "$python_minor" -ge 8 ]; then
            print_success "Python $python_version is compatible"
        else
            print_error "Python $python_version is not compatible. Python 3.8+ is required."
            return 1
        fi
    else
        print_error "Python 3 is not installed. Please install Python 3.8+ first."
        return 1
    fi
    
    # Check if conda is installed
    print_step "Checking if conda is installed..."
    if command_exists conda; then
        conda_version=$(conda --version 2>&1 | cut -d' ' -f2)
        print_success "Conda is installed (version: $conda_version)"
    else
        print_error "Conda is not installed. Please install Anaconda or Miniconda first."
        print_info "Download from: https://docs.conda.io/en/latest/miniconda.html"
        return 1
    fi
    
    # Check if git is installed
    print_step "Checking if git is installed..."
    if command_exists git; then
        print_success "Git is installed"
    else
        print_warning "Git is not installed. Some features may not work properly."
    fi
    
    # Check available disk space
    print_step "Checking available disk space..."
    if command_exists df; then
        free_space_gb=$(df . | awk 'NR==2 {print $4/1024/1024/1024}')
        if (( $(echo "$free_space_gb >= 10" | bc -l) )); then
            print_success "Available disk space: ${free_space_gb} GB"
        else
            print_warning "Available disk space: ${free_space_gb} GB (10+ GB recommended)"
        fi
    else
        print_warning "Could not check disk space"
    fi
    
    return 0
}

# Function to create conda environment
create_conda_environment() {
    print_header "Creating Conda Environment"
    
    local env_name="MuseTestEnv"
    
    # Check if environment already exists
    print_step "Checking if MuseTestEnv environment exists..."
    if conda env list | grep -q "$env_name"; then
        print_warning "Environment 'MuseTestEnv' already exists"
        read -p "Do you want to remove and recreate it? (y/N): " overwrite
        if [[ $overwrite =~ ^[Yy]$ ]]; then
            print_step "Removing existing environment..."
            run_command conda env remove -n "$env_name" -y || return 1
        else
            print_info "Using existing environment"
            return 0
        fi
    fi
    
    # Create environment with Python 3.8
    print_step "Creating MuseTestEnv environment with Python 3.8..."
    if run_command conda create -n "$env_name" python=3.8 -y; then
        print_success "Conda environment created successfully"
        return 0
    else
        print_error "Failed to create conda environment"
        return 1
    fi
}

# Function to install dependencies
install_dependencies() {
    print_header "Installing Dependencies"
    
    local env_name="MuseTestEnv"
    
    # Check if requirements.txt exists
    if [ ! -f "requirements.txt" ]; then
        print_error "requirements.txt not found in current directory"
        return 1
    fi
    
    # Install Python dependencies in the conda environment
    print_step "Installing Python dependencies..."
    if run_command conda run -n "$env_name" pip install -r requirements.txt; then
        print_success "Python dependencies installed successfully"
    else
        print_error "Failed to install Python dependencies"
        return 1
    fi
    
    # Check for additional system dependencies
    print_step "Checking for additional system dependencies..."
    
    # Check for FFmpeg
    if command_exists ffmpeg; then
        print_success "FFmpeg is installed"
    else
        print_warning "FFmpeg not found. You may need to install it manually."
        print_info "Download from: https://ffmpeg.org/download.html"
    fi
    
    # Check for CUDA (optional)
    if command_exists nvidia-smi; then
        if nvidia-smi >/dev/null 2>&1; then
            print_success "NVIDIA GPU detected"
            print_info "CUDA support available"
        else
            print_info "No NVIDIA GPU detected - will use CPU"
        fi
    else
        print_info "No NVIDIA GPU detected - will use CPU"
    fi
    
    return 0
}

# Function to verify installation
verify_installation() {
    print_header "Verifying Installation"
    
    local env_name="MuseTestEnv"
    
    # Test conda environment activation
    print_step "Testing conda environment activation..."
    if run_command conda run -n "$env_name" python -c "import sys; print('Python version:', sys.version)" >/dev/null 2>&1; then
        print_success "Conda environment activation works"
    else
        print_error "Conda environment activation failed"
        return 1
    fi
    
    # Test key package imports
    print_step "Testing key package imports..."
    local packages=("torch" "torchvision" "numpy" "opencv-python" "aiohttp" "asyncio")
    
    for package in "${packages[@]}"; do
        if conda run -n "$env_name" python -c "import $package; print('$package imported successfully')" >/dev/null 2>&1; then
            print_success "$package imported successfully"
        else
            print_warning "$package import failed"
        fi
    done
    
    return 0
}

# Function to setup initial configuration
setup_initial_configuration() {
    print_header "Initial Configuration"
    
    print_step "Setting up environment configuration..."
    
    # Create .env file if it doesn't exist
    if [ ! -f ".env" ]; then
        print_info "Creating initial .env file..."
        cat > .env << 'EOF'
# MuseTalk Server Configuration
# Generated by install_musetalk.sh

# MuseTalk inference server settings
MUSETALK_HOST=localhost
MUSETALK_PORT=8081

# Web interface server settings
WEB_HOST=localhost
WEB_PORT=8080
EOF
        print_success "Initial .env file created"
    else
        print_info ".env file already exists"
    fi
    
    # Make shell scripts executable
    print_step "Making shell scripts executable..."
    local scripts=("start_servers.sh" "install_musetalk.sh")
    
    for script in "${scripts[@]}"; do
        if [ -f "$script" ]; then
            if chmod +x "$script" 2>/dev/null; then
                print_success "Made $script executable"
            else
                print_warning "Could not make $script executable"
            fi
        fi
    done
}

# Function to create quick start guide
create_quick_start_guide() {
    print_header "Quick Start Guide"
    
    cat > QUICK_START.md << 'EOF'
# MuseTalk Quick Start Guide

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
EOF
    
    print_success "Quick start guide created (QUICK_START.md)"
}

# Main function
main() {
    print_header "MuseTalk All-in-One Installation"
    
    print_info "This script will install and configure MuseTalk for you."
    print_info "Make sure you have Anaconda or Miniconda installed."
    print_info "For more information, visit: https://docs.conda.io/en/latest/miniconda.html"
    
    # Ask for confirmation
    echo
    read -p "Do you want to proceed with the installation? (Y/n): " proceed
    if [[ $proceed =~ ^[Nn]$ ]]; then
        print_info "Installation cancelled"
        exit 0
    fi
    
    # Check system requirements
    if ! check_system_requirements; then
        print_error "System requirements not met. Please fix the issues above and try again."
        exit 1
    fi
    
    # Create conda environment
    if ! create_conda_environment; then
        print_error "Failed to create conda environment"
        exit 1
    fi
    
    # Install dependencies
    if ! install_dependencies; then
        print_error "Failed to install dependencies"
        exit 1
    fi
    
    # Verify installation
    if ! verify_installation; then
        print_warning "Installation verification failed. Some components may not work properly."
    fi
    
    # Setup initial configuration
    setup_initial_configuration
    
    # Create quick start guide
    create_quick_start_guide
    
    # Final success message
    print_header "Installation Complete!"
    print_success "MuseTalk has been successfully installed!"
    print_info "Next steps:"
    print_info "1. Configure your ports (optional): python create_env.py"
    print_info "2. Start the servers: python start_servers.py"
    print_info "3. Open your browser to: http://localhost:8080"
    print_info ""
    print_info "For detailed instructions, see: QUICK_START.md"
}

# Run main function
main "$@"
