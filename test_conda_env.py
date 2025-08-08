#!/usr/bin/env python3
"""
Test script to verify conda environment detection
"""

import subprocess
import os
import platform

def get_conda_environment_path():
    """Get the path to the conda environment"""
    try:
        # Try to get conda environment path
        if platform.system() == "Windows":
            result = subprocess.run(["conda", "info", "--envs"], capture_output=True, text=True, shell=True)
        else:
            result = subprocess.run(["conda", "info", "--envs"], capture_output=True, text=True)
        
        print(f"Conda env list command return code: {result.returncode}")
        print("Conda environments:")
        print(result.stdout)
        
        if result.returncode == 0:
            lines = result.stdout.split('\n')
            for line in lines:
                if 'MuseTestEnv' in line:
                    print(f"Found MuseTestEnv in line: {line}")
                    # Extract path from conda env list output
                    parts = line.split()
                    if len(parts) >= 2:
                        env_path = parts[-1]  # Last part is usually the path
                        print(f"Extracted environment path: {env_path}")
                        return env_path
        return None
    except Exception as e:
        print(f"Error getting conda environment path: {e}")
        return None

def get_python_executable():
    """Get the Python executable for the MuseTestEnv environment"""
    env_path = get_conda_environment_path()
    if env_path:
        if platform.system() == "Windows":
            python_path = os.path.join(env_path, "python.exe")
        else:
            python_path = os.path.join(env_path, "bin", "python")
        
        print(f"Looking for Python executable at: {python_path}")
        if os.path.exists(python_path):
            print(f"✓ Found Python executable: {python_path}")
            return python_path
        else:
            print(f"✗ Python executable not found at: {python_path}")
    
    print("Will use conda run as fallback")
    return None

def test_conda_run():
    """Test if conda run works"""
    try:
        print("\nTesting conda run...")
        result = subprocess.run(["conda", "run", "-n", "MuseTestEnv", "python", "--version"], 
                              capture_output=True, text=True)
        print(f"Conda run return code: {result.returncode}")
        print(f"stdout: {result.stdout}")
        print(f"stderr: {result.stderr}")
        return result.returncode == 0
    except Exception as e:
        print(f"Error testing conda run: {e}")
        return False

def main():
    print("Testing conda environment detection...")
    print("=" * 50)
    
    # Test environment detection
    env_path = get_conda_environment_path()
    if env_path:
        print(f"\n✓ Conda environment found at: {env_path}")
    else:
        print("\n✗ Conda environment not found")
    
    # Test Python executable detection
    python_executable = get_python_executable()
    if python_executable:
        print(f"\n✓ Python executable found: {python_executable}")
    else:
        print("\n✗ Python executable not found")
    
    # Test conda run
    if test_conda_run():
        print("\n✓ Conda run works")
    else:
        print("\n✗ Conda run failed")
    
    print("\nTest completed!")

if __name__ == "__main__":
    main()
