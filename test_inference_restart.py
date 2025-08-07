#!/usr/bin/env python3
"""
Test script to verify inference restart functionality
"""

import asyncio
import aiohttp
import time

async def test_inference_restart():
    """Test that inference can be restarted after completion"""
    
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
    base_url = f"http://{musetalk_host}:{musetalk_port}"
    
    async with aiohttp.ClientSession() as session:
        print("=== Testing Inference Restart Functionality ===")
        
        # Step 1: Check initial state
        print("\n1. Checking initial state...")
        try:
            async with session.get(f"{base_url}/stream_status") as response:
                data = await response.json()
                print(f"   Initial state: {data}")
                
                if data.get('inference_complete') or not data.get('inference_triggered'):
                    print("   ✓ System ready for inference")
                else:
                    print("   ⚠ System not ready, attempting reset...")
                    async with session.get(f"{base_url}/reset") as reset_response:
                        reset_data = await reset_response.json()
                        print(f"   Reset result: {reset_data}")
        except Exception as e:
            print(f"   ✗ Error checking initial state: {e}")
            return
        
        # Step 2: Start first inference
        print("\n2. Starting first inference...")
        try:
            async with session.get(f"{base_url}/start") as response:
                data = await response.json()
                print(f"   Start result: {data}")
                
                if not data.get('success'):
                    print("   ✗ Failed to start inference")
                    return
        except Exception as e:
            print(f"   ✗ Error starting inference: {e}")
            return
        
        # Step 3: Wait for inference to complete
        print("\n3. Waiting for inference to complete...")
        max_wait_time = 120  # 2 minutes
        start_time = time.time()
        
        while time.time() - start_time < max_wait_time:
            try:
                async with session.get(f"{base_url}/stream_status") as response:
                    data = await response.json()
                    
                    if data.get('inference_complete'):
                        print("   ✓ Inference completed!")
                        break
                    else:
                        elapsed = time.time() - start_time
                        print(f"   Waiting... ({elapsed:.1f}s elapsed)")
                        await asyncio.sleep(5)
            except Exception as e:
                print(f"   Error checking status: {e}")
                await asyncio.sleep(5)
        else:
            print("   ⚠ Timeout waiting for inference completion")
        
        # Step 4: Check if system is ready for new inference
        print("\n4. Checking if system is ready for new inference...")
        try:
            async with session.get(f"{base_url}/stream_status") as response:
                data = await response.json()
                print(f"   Final state: {data}")
                
                if data.get('inference_complete') or not data.get('inference_triggered'):
                    print("   ✓ System ready for new inference!")
                else:
                    print("   ✗ System not ready for new inference")
        except Exception as e:
            print(f"   ✗ Error checking final state: {e}")
        
        # Step 5: Try to start second inference
        print("\n5. Attempting to start second inference...")
        try:
            async with session.get(f"{base_url}/start") as response:
                data = await response.json()
                print(f"   Second start result: {data}")
                
                if data.get('success'):
                    print("   ✓ Successfully started second inference!")
                else:
                    print(f"   ✗ Failed to start second inference: {data.get('error')}")
        except Exception as e:
            print(f"   ✗ Error starting second inference: {e}")

if __name__ == "__main__":
    print("Inference Restart Test")
    print("Make sure the MuseTalk server is running on localhost:8081")
    print("=" * 50)
    
    asyncio.run(test_inference_restart())
