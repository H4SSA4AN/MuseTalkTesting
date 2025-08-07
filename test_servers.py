#!/usr/bin/env python3
"""
Test script to verify server communication and streaming
"""

import asyncio
import aiohttp
import sys
import time

# Configuration
MUSETALK_SERVER_URL = "http://localhost:8081"
WEB_SERVER_URL = "http://localhost:8080"

async def test_musetalk_server():
    """Test MuseTalk server endpoints"""
    print("Testing MuseTalk server...")
    
    async with aiohttp.ClientSession() as session:
        # Test stream status
        try:
            async with session.get(f"{MUSETALK_SERVER_URL}/stream_status") as response:
                if response.status == 200:
                    result = await response.json()
                    print(f"✓ Stream status: {result}")
                else:
                    print(f"✗ Stream status failed: {response.status}")
        except Exception as e:
            print(f"✗ Stream status error: {e}")
        
        # Test status endpoint
        try:
            async with session.get(f"{MUSETALK_SERVER_URL}/status") as response:
                if response.status == 200:
                    result = await response.json()
                    print(f"✓ Status endpoint: {result}")
                else:
                    print(f"✗ Status endpoint failed: {response.status}")
        except Exception as e:
            print(f"✗ Status endpoint error: {e}")
        
        # Test audio endpoint
        try:
            async with session.get(f"{MUSETALK_SERVER_URL}/audio") as response:
                if response.status == 200:
                    print(f"✓ Audio endpoint: {response.status}")
                else:
                    print(f"✗ Audio endpoint failed: {response.status}")
        except Exception as e:
            print(f"✗ Audio endpoint error: {e}")

async def test_web_server():
    """Test web server proxy endpoints"""
    print("\nTesting web server...")
    
    async with aiohttp.ClientSession() as session:
        # Test stream status proxy
        try:
            async with session.get(f"{WEB_SERVER_URL}/stream_status") as response:
                if response.status == 200:
                    result = await response.json()
                    print(f"✓ Web server stream status: {result}")
                else:
                    print(f"✗ Web server stream status failed: {response.status}")
        except Exception as e:
            print(f"✗ Web server stream status error: {e}")
        
        # Test status proxy
        try:
            async with session.get(f"{WEB_SERVER_URL}/status") as response:
                if response.status == 200:
                    result = await response.json()
                    print(f"✓ Web server status proxy: {result}")
                else:
                    print(f"✗ Web server status proxy failed: {response.status}")
        except Exception as e:
            print(f"✗ Web server status proxy error: {e}")
        
        # Test audio proxy
        try:
            async with session.get(f"{WEB_SERVER_URL}/audio") as response:
                if response.status == 200:
                    print(f"✓ Web server audio proxy: {response.status}")
                else:
                    print(f"✗ Web server audio proxy failed: {response.status}")
        except Exception as e:
            print(f"✗ Web server audio proxy error: {e}")

async def test_multiple_inference():
    """Test multiple inference runs"""
    print("\nTesting multiple inference runs...")
    
    async with aiohttp.ClientSession() as session:
        # First inference run
        print("Starting first inference...")
        try:
            async with session.get(f"{MUSETALK_SERVER_URL}/start") as response:
                if response.status == 200:
                    result = await response.json()
                    print(f"✓ First inference started: {result}")
                    
                    # Wait for inference to complete
                    await asyncio.sleep(10)
                    
                    # Check status
                    async with session.get(f"{MUSETALK_SERVER_URL}/status") as status_response:
                        if status_response.status == 200:
                            status = await status_response.json()
                            print(f"✓ First inference status: {status}")
                    
                    # Test reset
                    print("Testing reset...")
                    async with session.get(f"{MUSETALK_SERVER_URL}/reset") as reset_response:
                        if reset_response.status == 200:
                            reset_result = await reset_response.json()
                            print(f"✓ Reset successful: {reset_result}")
                    
                    # Second inference run
                    print("Starting second inference...")
                    await asyncio.sleep(2)
                    
                    async with session.get(f"{MUSETALK_SERVER_URL}/start") as response2:
                        if response2.status == 200:
                            result2 = await response2.json()
                            print(f"✓ Second inference started: {result2}")
                        else:
                            print(f"✗ Second inference failed: {response2.status}")
                    
                else:
                    print(f"✗ First inference failed: {response.status}")
        except Exception as e:
            print(f"✗ Multiple inference test error: {e}")

async def test_stream_connection():
    """Test if streaming connection can be established"""
    print("\nTesting stream connection...")
    
    async with aiohttp.ClientSession() as session:
        try:
            # Start inference
            async with session.get(f"{MUSETALK_SERVER_URL}/start") as response:
                if response.status == 200:
                    result = await response.json()
                    print(f"✓ Inference started: {result}")
                    
                    # Wait a moment for inference to begin
                    await asyncio.sleep(2)
                    
                    # Try to connect to stream
                    try:
                        async with session.get(f"{MUSETALK_SERVER_URL}/stream") as stream_response:
                            if stream_response.status == 200:
                                print("✓ Stream connection established")
                                
                                # Read a few chunks to test streaming
                                chunk_count = 0
                                async for chunk in stream_response.content.iter_chunked(1024):
                                    chunk_count += 1
                                    if chunk_count >= 5:  # Test first 5 chunks
                                        print(f"✓ Stream chunks received: {chunk_count}")
                                        break
                            else:
                                print(f"✗ Stream connection failed: {stream_response.status}")
                    except Exception as e:
                        print(f"✗ Stream connection error: {e}")
                else:
                    print(f"✗ Inference start failed: {response.status}")
        except Exception as e:
            print(f"✗ Inference start error: {e}")

async def main():
    """Main test function"""
    print("Testing MuseTalk separated servers...")
    print("=" * 50)
    
    # Test individual servers
    await test_musetalk_server()
    await test_web_server()
    
    # Test multiple inference runs
    await test_multiple_inference()
    
    # Test streaming
    await test_stream_connection()
    
    print("\n" + "=" * 50)
    print("Test completed!")

if __name__ == "__main__":
    asyncio.run(main())
