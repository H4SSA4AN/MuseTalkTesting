"""
Streaming handler for MuseTalk MJPEG streaming
"""

import asyncio
import cv2
import time
from state_manager import InferenceState


class StreamingHandler:
    """Handles MJPEG streaming of processed frames"""
    
    def __init__(self, state: InferenceState, avatar_manager):
        self.state = state
        self.avatar_manager = avatar_manager
        self.avatar = avatar_manager.get_avatar()
        self.audio_length = avatar_manager.get_audio_length()
    
    async def mjpeg_response(self):
        """Generate MJPEG response for streaming"""
        boundary = "frame"
        # Get current FPS from avatar to respect user settings
        # This ensures the playback frame rate matches the user's FPS setting
        current_fps = self.avatar.fps if self.avatar else self.avatar_manager.get_fps()
        frame_delay = 1.0 / current_fps
        start_time = asyncio.get_event_loop().time()
        frame_count = 0
        
        print(f"Starting MJPEG stream with FPS: {current_fps} (frame delay: {frame_delay:.3f}s)")
        
        while True:
            # Wait for frames to be available in buffer
            while self.state.get_buffer_size() == 0 and not self.state.inference_complete:
                await asyncio.sleep(0.01)
            
            # Get frame from buffer
            frame = self.state.get_frame_from_buffer()
            
            # Check if we have a frame
            if frame is None:
                if self.state.inference_complete:
                    # End of stream signal
                    print("Stream complete - no more frames")
                    self._log_stream_completion()
                    break
                else:
                    # No frame available yet, continue waiting
                    continue
            
            frame_count += 1
            
            # Calculate when this frame should be displayed
            target_time = start_time + (frame_count * frame_delay)
            current_time = asyncio.get_event_loop().time()
            
            # Wait if we're ahead of schedule
            if current_time < target_time:
                await asyncio.sleep(target_time - current_time)
            
            # Convert numpy frame to JPEG
            try:
                ret, jpeg = cv2.imencode('.jpg', frame)
                if not ret:
                    print(f"Failed to encode frame {frame_count}")
                    continue
                    
                # Yield the MJPEG frame
                frame_data = (b"--" + boundary.encode() + b"\r\n"
                             b"Content-Type: image/jpeg\r\n"
                             b"Content-Length: " + str(len(jpeg)).encode() + b"\r\n\r\n" + jpeg.tobytes() + b"\r\n")
                
                yield frame_data
                
                # Debug: Print frame count every 30 frames
                if frame_count % 30 == 0:
                    print(f"Streamed {frame_count} frames")
                    
            except Exception as e:
                print(f"Error processing frame {frame_count}: {e}")
                continue
    
    def _log_stream_completion(self):
        """Log stream completion with timing information"""
        stream_end_time = time.time()
        if self.state.inference_end_time is not None:
            streaming_duration = stream_end_time - self.state.inference_end_time
            print(f"Streaming finished. Time from inference end to stream end: {streaming_duration:.2f} seconds")
        else:
            print("Streaming finished (inference end time not available)")
        
        # Mark as ready for new inference
        print("System ready for new inference run")
