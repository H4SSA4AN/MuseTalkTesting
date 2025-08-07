#!/usr/bin/env python3
"""
Dedicated script to run MuseTalk server in MuseTestEnv environment
"""

import subprocess
import sys
import os
import platform

def run_in_musetalk_env():
    """Run the MuseTalk server in MuseTestEnv environment"""
    
    print("Starting MuseTalk inference server in MuseTestEnv environment...")
    print(f"Server will be available at: http://localhost:8081")
    
    try:
        if platform.system() == "Windows":
            # Windows: Use conda activate
            cmd = ["cmd", "/c", "conda activate MuseTestEnv && python musetalkServer/server.py"]
            subprocess.run(cmd, shell=True, check=True)
        else:
            # Unix/Linux: Use conda run
            cmd = ["conda", "run", "-n", "MuseTestEnv", "python", "musetalkServer/server.py"]
            subprocess.run(cmd, check=True)
            
    except KeyboardInterrupt:
        print("\nMuseTalk server stopped by user")
    except subprocess.CalledProcessError as e:
        print(f"Error running MuseTalk server: {e}")
        print("Make sure MuseTestEnv environment is properly set up")
    except FileNotFoundError:
        print("Error: conda not found. Make sure conda is installed and in PATH")
    except Exception as e:
        print(f"Unexpected error: {e}")

def check_environment():
    """Check if MuseTestEnv environment exists and is accessible"""
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
    """Main function"""
    print("MuseTalk Server Launcher")
    print("=" * 30)
    
    # Check if MuseTestEnv exists
    if not check_environment():
        print("Cannot start MuseTalk server without MuseTestEnv environment.")
        sys.exit(1)
    
    # Run the server
    run_in_musetalk_env()

if __name__ == "__main__":
    main()
