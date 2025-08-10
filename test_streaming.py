#!/usr/bin/env python3
"""
Simple test script to verify streaming functionality
"""

import asyncio
import cv2
import numpy as np
import time
from collections import deque

class TestStreamingState:
    def __init__(self):
        self.frame_buffer = deque(maxlen=100)
        self.streaming_started = True
        self.stream_ready = True
        self.inference_complete = False
    
    def add_frame_to_buffer(self, frame):
        self.frame_buffer.append(frame)
    
    def get_buffer_size(self):
        return len(self.frame_buffer)
    
    def get_frame_from_buffer(self):
        if self.frame_buffer:
            return self.frame_buffer.popleft()
        return None

async def test_mjpeg_streaming():
    """Test MJPEG streaming with dummy frames"""
    state = TestStreamingState()
    
    # Generate some test frames
    for i in range(10):
        # Create a simple test frame
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        # Add some text to the frame
        cv2.putText(frame, f"Test Frame {i}", (50, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
        state.add_frame_to_buffer(frame)
        await asyncio.sleep(0.1)  # Simulate processing time
    
    print(f"Added {state.get_buffer_size()} test frames to buffer")
    
    # Test MJPEG response generation
    boundary = "frame"
    frame_count = 0
    
    while True:
        frame = state.get_frame_from_buffer()
        if frame is None:
            break
        
        frame_count += 1
        print(f"Processing frame {frame_count}")
        
        # Convert to JPEG
        ret, jpeg = cv2.imencode('.jpg', frame)
        if ret:
            print(f"Frame {frame_count} encoded successfully, size: {len(jpeg)} bytes")
        else:
            print(f"Frame {frame_count} encoding failed")
    
    print(f"Test completed. Processed {frame_count} frames.")

if __name__ == "__main__":
    asyncio.run(test_mjpeg_streaming())
