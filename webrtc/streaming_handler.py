"""
Streaming handler for MuseTalk frame processing and MJPEG streaming
"""

import asyncio
import cv2
import numpy as np
import time
import math
from musetalk.utils.blending import get_image_blending
from state_manager import StreamingState


class StreamingHandler:
    """Handles frame processing and MJPEG streaming"""
    
    def __init__(self, state: StreamingState, avatar_manager):
        self.state = state
        self.avatar_manager = avatar_manager
        self.avatar = avatar_manager.get_avatar()
        self.audio_length = avatar_manager.get_audio_length()
    
    def create_custom_process_frames(self, loop):
        """Create a custom process_frames function that streams frames as they're processed"""
        
        def custom_process_frames(res_frame_queue, video_len, skip_save_images):
            self.state.inference_start_time = time.time()
            self.state.batches_processed = 0
            self.state.total_batches_expected = (video_len + self.avatar.batch_size - 1) // self.avatar.batch_size
            
            print(f"Starting inference with {video_len} frames, {self.state.total_batches_expected} batches expected")
            
            idx = 0
            current_batch = 0
            while idx < video_len:
                try:
                    # Get frame from the original inference queue
                    res_frame = res_frame_queue.get(block=True, timeout=1)
                    
                    # Process the frame
                    processed_frame = self._process_single_frame(res_frame, idx)
                    if processed_frame is not None:
                        # Add frame to buffer immediately for streaming
                        asyncio.run_coroutine_threadsafe(
                            self._add_frame_to_buffer(processed_frame), loop
                        )
                    
                    idx += 1
                    
                    # Track batch completion
                    if idx % self.avatar.batch_size == 0:
                        current_batch += 1
                        self.state.batches_processed = current_batch
                        
                        # Check if we should start streaming
                        self._check_stream_ready()
                        
                        # Debug: Print current batch progress
                        self._print_batch_progress(current_batch)
                    
                except Exception as e:
                    print(f"Error processing frame {idx}: {e}")
                    continue
            
            # Handle remaining frames in the last batch
            if idx % self.avatar.batch_size != 0:
                self.state.batches_processed = current_batch + 1
            
            # Signal end of inference
            asyncio.run_coroutine_threadsafe(
                self._add_frame_to_buffer(None), loop
            )
            self.state.complete_inference()
            print(f"Inference completed. Total batches processed: {self.state.batches_processed}")
        
        return custom_process_frames
    
    def _process_single_frame(self, res_frame, idx):
        """Process a single frame"""
        try:
            # Get frame data from avatar
            bbox = self.avatar.coord_list_cycle[idx % (len(self.avatar.coord_list_cycle))]
            ori_frame = self.avatar.frame_list_cycle[idx % (len(self.avatar.frame_list_cycle))]
            x1, y1, x2, y2 = bbox
            
            # Resize the result frame
            try:
                res_frame = cv2.resize(res_frame.astype(np.uint8), (x2 - x1, y2 - y1))
            except:
                return None
            
            # Get mask data
            mask = self.avatar.mask_list_cycle[idx % (len(self.avatar.mask_list_cycle))]
            mask_crop_box = self.avatar.mask_coords_list_cycle[idx % (len(self.avatar.mask_coords_list_cycle))]
            
            # Blend the frames
            combine_frame = get_image_blending(ori_frame, res_frame, bbox, mask, mask_crop_box)
            return combine_frame
            
        except Exception as e:
            print(f"Error processing frame {idx}: {e}")
            return None
    
    def _check_stream_ready(self):
        """Check if stream should be ready to start"""
        elapsed_time = time.time() - self.state.inference_start_time
        if elapsed_time > 0 and self.state.batches_processed > 0:
            processing_rate = self.state.batches_processed / elapsed_time
            self.state.estimated_inference_time = self.state.total_batches_expected / processing_rate
            estimated_time_remaining = self.state.estimated_inference_time - elapsed_time
            
            # Start streaming when estimated time remaining equals audio length
            if estimated_time_remaining <= self.audio_length and not self.state.stream_ready:
                self.state.set_stream_ready()
                print(f"Stream ready! Batch {self.state.batches_processed}/{self.state.total_batches_expected}")
                print(f"Estimated time remaining: {estimated_time_remaining:.1f}s, Audio length: {self.audio_length:.1f}s")
    
    def _print_batch_progress(self, current_batch):
        """Print batch progress for debugging"""
        if current_batch % 2 == 0:  # Print every 2nd batch to avoid spam
            elapsed_time = time.time() - self.state.inference_start_time
            if elapsed_time > 0:
                estimated_remaining = (self.state.total_batches_expected / (self.state.batches_processed / elapsed_time)) - elapsed_time
                print(f"Batch {current_batch}/{self.state.total_batches_expected} completed, frames in buffer: {self.state.get_buffer_size()}, time remaining: {estimated_remaining:.1f}s")
            else:
                print(f"Batch {current_batch}/{self.state.total_batches_expected} completed, frames in buffer: {self.state.get_buffer_size()}")
    
    async def _add_frame_to_buffer(self, frame):
        """Add a frame to the buffer"""
        self.state.add_frame_to_buffer(frame)
    
    async def mjpeg_response(self):
        """Generate MJPEG response for streaming"""
        boundary = "frame"
        frame_delay = 1.0 / self.avatar_manager.get_fps()
        start_time = asyncio.get_event_loop().time()
        frame_count = 0
        
        while True:
            # Wait for frames to be available in buffer
            while self.state.get_buffer_size() == 0 and not self.state.inference_complete:
                await asyncio.sleep(0.01)
            
            # Get frame from buffer
            frame = self.state.get_frame_from_buffer()
            if frame is None:
                # No more frames and inference is complete
                break
            
            frame_count += 1
            
            if frame is None:
                # End of stream signal
                self._log_stream_completion()
                break
            
            # Calculate when this frame should be displayed
            target_time = start_time + (frame_count * frame_delay)
            current_time = asyncio.get_event_loop().time()
            
            # Wait if we're ahead of schedule
            if current_time < target_time:
                await asyncio.sleep(target_time - current_time)
            
            # Convert numpy frame to JPEG
            ret, jpeg = cv2.imencode('.jpg', frame)
            if not ret:
                continue
                
            yield (b"--" + boundary.encode() + b"\r\n"
                   b"Content-Type: image/jpeg\r\n"
                   b"Content-Length: " + str(len(jpeg)).encode() + b"\r\n\r\n" + jpeg.tobytes() + b"\r\n")
    
    def _log_stream_completion(self):
        """Log stream completion with timing information"""
        stream_end_time = time.time()
        if self.state.inference_end_time is not None:
            streaming_duration = stream_end_time - self.state.inference_end_time
            print(f"Streaming finished. Time from inference end to stream end: {streaming_duration:.2f} seconds")
        else:
            print("Streaming finished (inference end time not available)") 