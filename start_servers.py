#!/usr/bin/env python3
"""
Startup script for MuseTalk with separated web interface and inference servers
"""

import subprocess
import sys
import os
import time
import signal
import threading
import platform
from pathlib import Path

def load_env_file():
    """Load environment variables from .env file if it exists"""
    env_file = ".env"
    if os.path.exists(env_file):
        print(f"Loading environment variables from {env_file}")
        with open(env_file, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    os.environ[key] = value
        print("Environment variables loaded successfully")
    else:
        print("No .env file found, using default configuration")
        print("Run 'python create_env.py' to create a custom configuration")

def get_conda_environment_path():
    """Get the path to the conda environment"""
    try:
        # Try to get conda environment path
        if platform.system() == "Windows":
            result = subprocess.run(["conda", "info", "--envs"], capture_output=True, text=True, shell=True)
        else:
            result = subprocess.run(["conda", "info", "--envs"], capture_output=True, text=True)
        
        if result.returncode == 0:
            lines = result.stdout.split('\n')
            for line in lines:
                if 'MuseTestEnv' in line and '*' not in line:  # Not the active environment
                    # Extract path from conda env list output
                    parts = line.split()
                    if len(parts) >= 2:
                        return parts[-1]  # Last part is usually the path
        return None
    except Exception as e:
        print(f"Warning: Could not determine conda environment path: {e}")
        return None

def get_python_executable():
    """Get the Python executable for the MuseTestEnv environment"""
    env_path = get_conda_environment_path()
    if env_path:
        if platform.system() == "Windows":
            python_path = os.path.join(env_path, "python.exe")
        else:
            python_path = os.path.join(env_path, "bin", "python")
        
        if os.path.exists(python_path):
            return python_path
    
    # Fallback: try to use conda run
    return None

def run_musetalk_server():
    """Run the MuseTalk inference server in the MuseTestEnv environment"""
    # Get port from environment or use default
    musetalk_port = os.getenv("MUSETALK_PORT", "8081")
    musetalk_host = os.getenv("MUSETALK_HOST", "localhost")
    
    print(f"Starting MuseTalk inference server on {musetalk_host}:{musetalk_port} in MuseTestEnv environment...")
    
    # Set environment variables for the server
    env = os.environ.copy()
    env["MUSETALK_HOST"] = musetalk_host
    env["MUSETALK_PORT"] = musetalk_port
    
    try:
        python_executable = get_python_executable()
        
        if python_executable:
            # Use the specific Python executable from the conda environment
            cmd = [python_executable, "musetalkServer/server.py"]
            print(f"Using Python executable: {python_executable}")
            subprocess.run(cmd, env=env, check=True)
        else:
            # Fallback: try conda run (works better on remote servers)
            cmd = ["conda", "run", "-n", "MuseTestEnv", "python", "musetalkServer/server.py"]
            print("Using conda run to execute server")
            subprocess.run(cmd, env=env, check=True)
            
    except KeyboardInterrupt:
        print("MuseTalk server stopped by user")
    except subprocess.CalledProcessError as e:
        print(f"Error running MuseTalk server: {e}")
        print(f"Command returned exit code: {e.returncode}")
        if e.stdout:
            print(f"stdout: {e.stdout}")
        if e.stderr:
            print(f"stderr: {e.stderr}")
    except Exception as e:
        print(f"Error running MuseTalk server: {e}")

def run_web_server():
    """Run the web interface server"""
    # Get port from environment or use default
    web_port = os.getenv("WEB_PORT", "8080")
    web_host = os.getenv("WEB_HOST", "localhost")
    
    print(f"Starting web interface server on {web_host}:{web_port}...")
    
    # Set environment variables for the server
    env = os.environ.copy()
    env["WEB_HOST"] = web_host
    env["WEB_PORT"] = web_port
    
    try:
        subprocess.run([sys.executable, "webrtc/server.py"], env=env, check=True)
    except KeyboardInterrupt:
        print("Web server stopped by user")
    except subprocess.CalledProcessError as e:
        print(f"Error running web server: {e}")
        print(f"Command returned exit code: {e.returncode}")
        if e.stdout:
            print(f"stdout: {e.stdout}")
        if e.stderr:
            print(f"stderr: {e.stderr}")
    except Exception as e:
        print(f"Error running web server: {e}")

def check_environment():
    """Check if MuseTestEnv environment exists"""
    try:
        if platform.system() == "Windows":
            result = subprocess.run(["conda", "env", "list"], capture_output=True, text=True, shell=True)
        else:
            result = subprocess.run(["conda", "env", "list"], capture_output=True, text=True)
        
        if result.returncode == 0 and "MuseTestEnv" in result.stdout:
            print("✓ MuseTestEnv environment found")
            return True
        else:
            print("✗ MuseTestEnv environment not found")
            print("Please create the environment first:")
            print("conda env create -f environment.yml")
            return False
    except Exception as e:
        print(f"Error checking conda environment: {e}")
        return False

def main():
    """Main function to start both servers"""
    print("Starting MuseTalk with separated servers...")
    
    # Load environment variables
    load_env_file()
    
    # Get port numbers from environment
    musetalk_port = os.getenv("MUSETALK_PORT", "8081")
    web_port = os.getenv("WEB_PORT", "8080")
    musetalk_host = os.getenv("MUSETALK_HOST", "localhost")
    web_host = os.getenv("WEB_HOST", "localhost")
    
    print(f"MuseTalk inference server will run on {musetalk_host}:{musetalk_port} (in MuseTestEnv)")
    print(f"Web interface server will run on {web_host}:{web_port}")
    print("Press Ctrl+C to stop both servers")
    
    # Check if MuseTestEnv exists
    if not check_environment():
        print("Cannot start MuseTalk server without MuseTestEnv environment.")
        print("Please create the environment and try again.")
        sys.exit(1)
    
    # Start MuseTalk server in a separate thread
    musetalk_thread = threading.Thread(target=run_musetalk_server, daemon=True)
    musetalk_thread.start()
    
    # Wait a moment for MuseTalk server to initialize
    print("Waiting for MuseTalk server to initialize...")
    time.sleep(5)
    
    # Start web server in main thread
    run_web_server()

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nShutting down servers...")
        sys.exit(0)
