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

def get_activate_command():
    """Get the appropriate activation command based on the platform"""
    if platform.system() == "Windows":
        # For Windows, use the batch file to activate conda environment
        return ["cmd", "/c", "conda activate MuseTestEnv &&"]
    else:
        # For Unix/Linux, use source command
        return ["bash", "-c", "source activate MuseTestEnv &&"]

def run_musetalk_server():
    """Run the MuseTalk inference server in the MuseTestEnv environment"""
    print("Starting MuseTalk inference server in MuseTestEnv environment...")
    try:
        if platform.system() == "Windows":
            # Windows: Use conda activate
            cmd = ["cmd", "/c", "conda activate MuseTestEnv && python musetalkServer/server.py"]
            subprocess.run(cmd, shell=True, check=True)
        else:
            # Unix/Linux: Use source activate
            cmd = ["bash", "-c", "source activate MuseTestEnv && python musetalkServer/server.py"]
            subprocess.run(cmd, check=True)
    except KeyboardInterrupt:
        print("MuseTalk server stopped by user")
    except Exception as e:
        print(f"Error running MuseTalk server: {e}")

def run_web_server():
    """Run the web interface server"""
    print("Starting web interface server...")
    try:
        subprocess.run([sys.executable, "webrtc/server.py"], check=True)
    except KeyboardInterrupt:
        print("Web server stopped by user")
    except Exception as e:
        print(f"Error running web server: {e}")

def check_environment():
    """Check if MuseTestEnv environment exists"""
    try:
        if platform.system() == "Windows":
            result = subprocess.run(["conda", "env", "list"], capture_output=True, text=True, shell=True)
        else:
            result = subprocess.run(["conda", "env", "list"], capture_output=True, text=True)
        
        if "MuseTestEnv" in result.stdout:
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
    print("MuseTalk inference server will run on port 8081 (in MuseTestEnv)")
    print("Web interface server will run on port 8080")
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
