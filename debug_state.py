#!/usr/bin/env python3
"""
Debug script to check MuseTalk server state
"""

import asyncio
import aiohttp
import json

async def debug_server_state():
    """Debug the current server state"""
    
    base_url = "http://localhost:8081"
    
    async with aiohttp.ClientSession() as session:
        print("=== MuseTalk Server State Debug ===")
        
        # Check stream status
        print("\n1. Stream Status:")
        try:
            async with session.get(f"{base_url}/stream_status") as response:
                if response.status == 200:
                    data = await response.json()
                    print(f"   Stream Ready: {data.get('stream_ready', 'N/A')}")
                    print(f"   Inference Complete: {data.get('inference_complete', 'N/A')}")
                    print(f"   Inference Triggered: {data.get('inference_triggered', 'N/A')}")
                    print(f"   Ready for New Inference: {data.get('ready_for_new_inference', 'N/A')}")
                    print(f"   Batches Processed: {data.get('batches_processed', 'N/A')}")
                    print(f"   Total Batches Expected: {data.get('total_batches_expected', 'N/A')}")
                    print(f"   Frames in Buffer: {data.get('frames_in_buffer', 'N/A')}")
                else:
                    print(f"   Error: {response.status}")
        except Exception as e:
            print(f"   Error: {e}")
        
        # Check settings
        print("\n2. Current Settings:")
        try:
            async with session.get(f"{base_url}/get_settings") as response:
                if response.status == 200:
                    data = await response.json()
                    print(f"   FPS: {data.get('fps', 'N/A')}")
                    print(f"   Batch Size: {data.get('batch_size', 'N/A')}")
                else:
                    print(f"   Error: {response.status}")
        except Exception as e:
            print(f"   Error: {e}")
        
        # Try to start inference
        print("\n3. Try to Start Inference:")
        try:
            async with session.get(f"{base_url}/start") as response:
                if response.status == 200:
                    data = await response.json()
                    print(f"   Success: {data.get('success', 'N/A')}")
                    print(f"   Message: {data.get('message', 'N/A')}")
                else:
                    print(f"   Error: {response.status}")
                    data = await response.json()
                    print(f"   Error Message: {data.get('error', 'N/A')}")
        except Exception as e:
            print(f"   Error: {e}")
        
        # Check if reset is needed
        print("\n4. Reset Status:")
        try:
            async with session.get(f"{base_url}/reset") as response:
                if response.status == 200:
                    data = await response.json()
                    print(f"   Reset Success: {data.get('success', 'N/A')}")
                    print(f"   Reset Message: {data.get('message', 'N/A')}")
                else:
                    print(f"   Reset Error: {response.status}")
        except Exception as e:
            print(f"   Reset Error: {e}")
        
        # Check stream status again after reset
        print("\n5. Stream Status After Reset:")
        try:
            async with session.get(f"{base_url}/stream_status") as response:
                if response.status == 200:
                    data = await response.json()
                    print(f"   Stream Ready: {data.get('stream_ready', 'N/A')}")
                    print(f"   Inference Complete: {data.get('inference_complete', 'N/A')}")
                    print(f"   Inference Triggered: {data.get('inference_triggered', 'N/A')}")
                    print(f"   Ready for New Inference: {data.get('ready_for_new_inference', 'N/A')}")
                else:
                    print(f"   Error: {response.status}")
        except Exception as e:
            print(f"   Error: {e}")

if __name__ == "__main__":
    print("MuseTalk Server State Debug Tool")
    print("Make sure the MuseTalk server is running on localhost:8081")
    print("=" * 50)
    
    asyncio.run(debug_server_state())
