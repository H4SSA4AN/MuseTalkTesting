#!/usr/bin/env python3
"""
Test script for the new settings API endpoints
"""

import asyncio
import aiohttp
import json

async def test_settings_api():
    """Test the settings API endpoints"""
    
    # Load environment variables
    import os
    if os.path.exists('.env'):
        with open('.env', 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    os.environ[key] = value
    
    musetalk_host = os.getenv("MUSETALK_HOST", "localhost")
    musetalk_port = os.getenv("MUSETALK_PORT", "8081")
    base_url = f"http://{musetalk_host}:{musetalk_port}"  # MuseTalk server
    
    async with aiohttp.ClientSession() as session:
        print("Testing Settings API endpoints...")
        
        # Test 1: Get current settings
        print("\n1. Testing GET /get_settings")
        try:
            async with session.get(f"{base_url}/get_settings") as response:
                if response.status == 200:
                    data = await response.json()
                    print(f"✓ GET /get_settings successful: {data}")
                else:
                    print(f"✗ GET /get_settings failed: {response.status}")
        except Exception as e:
            print(f"✗ GET /get_settings error: {e}")
        
        # Test 2: Update settings
        print("\n2. Testing POST /update_settings")
        test_settings = {
            "fps": 30,
            "batch_size": 8
        }
        try:
            async with session.post(f"{base_url}/update_settings", json=test_settings) as response:
                if response.status == 200:
                    data = await response.json()
                    print(f"✓ POST /update_settings successful: {data}")
                else:
                    print(f"✗ POST /update_settings failed: {response.status}")
        except Exception as e:
            print(f"✗ POST /update_settings error: {e}")
        
        # Test 3: Get settings again to verify update
        print("\n3. Testing GET /get_settings (after update)")
        try:
            async with session.get(f"{base_url}/get_settings") as response:
                if response.status == 200:
                    data = await response.json()
                    print(f"✓ GET /get_settings successful: {data}")
                else:
                    print(f"✗ GET /get_settings failed: {response.status}")
        except Exception as e:
            print(f"✗ GET /get_settings error: {e}")
        
        # Test 4: Test invalid settings
        print("\n4. Testing POST /update_settings with invalid values")
        invalid_settings = {
            "fps": 100,  # Invalid: too high
            "batch_size": 0  # Invalid: too low
        }
        try:
            async with session.post(f"{base_url}/update_settings", json=invalid_settings) as response:
                if response.status == 200:
                    data = await response.json()
                    print(f"✓ POST /update_settings validation working: {data}")
                else:
                    print(f"✗ POST /update_settings failed: {response.status}")
        except Exception as e:
            print(f"✗ POST /update_settings error: {e}")
        
        # Test 5: Test different FPS values
        print("\n5. Testing different FPS values")
        test_fps_values = [15, 25, 30, 60]
        for fps in test_fps_values:
            print(f"   Testing FPS: {fps}")
            test_settings = {"fps": fps, "batch_size": 4}
            try:
                async with session.post(f"{base_url}/update_settings", json=test_settings) as response:
                    if response.status == 200:
                        data = await response.json()
                        print(f"   ✓ FPS {fps} set successfully")
                    else:
                        print(f"   ✗ FPS {fps} failed: {response.status}")
            except Exception as e:
                print(f"   ✗ FPS {fps} error: {e}")
        
        # Reset to default values
        print("\n6. Resetting to default values")
        default_settings = {"fps": 25, "batch_size": 4}
        try:
            async with session.post(f"{base_url}/update_settings", json=default_settings) as response:
                if response.status == 200:
                    print("✓ Reset to default values successful")
                else:
                    print(f"✗ Reset failed: {response.status}")
        except Exception as e:
            print(f"✗ Reset error: {e}")

if __name__ == "__main__":
    print("Settings API Test Script")
    print("Make sure the MuseTalk server is running on localhost:8081")
    print("=" * 50)
    
    asyncio.run(test_settings_api())
