#!/usr/bin/env python3
"""
Test script to verify environment variable loading
"""

import os

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
                    print(f"  {key} = {value}")
        print("Environment variables loaded successfully")
    else:
        print("No .env file found")

def main():
    print("Testing environment variable loading...")
    print("=" * 50)
    
    # Load environment variables
    load_env_file()
    
    # Check the values
    print("\nCurrent environment variable values:")
    print(f"MUSETALK_HOST = {os.getenv('MUSETALK_HOST', 'localhost (default)')}")
    print(f"MUSETALK_PORT = {os.getenv('MUSETALK_PORT', '8081 (default)')}")
    print(f"WEB_HOST = {os.getenv('WEB_HOST', 'localhost (default)')}")
    print(f"WEB_PORT = {os.getenv('WEB_PORT', '8080 (default)')}")
    
    print("\nTest completed!")

if __name__ == "__main__":
    main()
