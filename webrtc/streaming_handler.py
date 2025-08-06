"""
Streaming handler for MuseTalk frame processing and MJPEG streaming
"""

import asyncio
import cv2
import numpy as np
import time
import math
import queue
from musetalk.utils.blending import get_image_blending
from state_manager import StreamingState


class StreamingHandler:
    """Handles frame processing and MJPEG streaming"""
    
    def __init__(self, state: StreamingState, avatar_manager, initial_fps=None):
        self.state = state
        self.avatar_manager = avatar_manager
        self.avatar = avatar_manager.get_avatar()
        self.audio_length = avatar_manager.get_audio_length()
        # Store the initial FPS for frame delay calculations
        self.initial_fps = initial_fps if initial_fps is not None else avatar_manager.get_fps()
        # Use a thread-safe queue for frame buffering
        self.frame_queue = queue.Queue(maxsize=1000)
    
    def create_custom_process_frames(self, loop):
        """Create a custom process_frames function that streams frames as they're processed"""
        
        def custom_process_frames(res_frame_queue, video_len, skip_save_images):
            self.state.inference_start_time = time.time()
            self.state.batches_processed = 0
            self.state.total_batches_expected = (video_len + self.avatar.batch_size - 1) // self.avatar.batch_size
            
            print(f"Starting inference with {video_len} frames, {self.state.total_batches_expected} batches expected")
            print(f"Inference start time set to: {self.state.inference_start_time}")
            print(f"Audio length: {self.audio_length}s, Target FPS: {self.initial_fps}")
            
            idx = 0
            current_batch = 0
            while idx < video_len:
                try:
                    # Get frame from the original inference queue
                    res_frame = res_frame_queue.get(block=True, timeout=1)
                    
                    # Process the frame
                    processed_frame = self._process_single_frame(res_frame, idx)
                    if processed_frame is not None:
                        # Add frame to queue immediately for streaming
                        try:
                            self.frame_queue.put(processed_frame, block=False)
                            if idx % 5 == 0:  # Log every 5th frame for more frequent updates
                                print(f"Added frame {idx} to queue, queue size: {self.frame_queue.qsize()}")
                        except queue.Full:
                            # If queue is full, remove oldest frame and add new one
                            try:
                                self.frame_queue.get_nowait()
                                self.frame_queue.put(processed_frame, block=False)
                                print(f"Queue full, replaced frame {idx}")
                            except:
                                print(f"Failed to add frame {idx} to queue")
                                pass  # Skip frame if still can't add
                    else:
                        print(f"Failed to process frame {idx}")
                    
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
            try:
                self.frame_queue.put(None, block=False)  # End signal
            except:
                pass
            self.state.complete_inference()
            print(f"Inference completed. Total batches processed: {self.state.batches_processed}")
            print("Server now in listening state, waiting for next inference request...")
        
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
            
            # Debug logging for stream ready check
            if self.state.batches_processed % 2 == 0:  # Log every 2nd batch
                print(f"Stream ready check - Batch {self.state.batches_processed}/{self.state.total_batches_expected}")
                print(f"  Elapsed time: {elapsed_time:.1f}s, Processing rate: {processing_rate:.2f} batches/s")
                print(f"  Estimated total time: {self.state.estimated_inference_time:.1f}s")
                print(f"  Estimated time remaining: {estimated_time_remaining:.1f}s, Audio length: {self.audio_length:.1f}s")
                print(f"  Stream ready: {self.state.stream_ready}")
            
            # Start streaming when estimated time remaining equals audio length
            if estimated_time_remaining <= self.audio_length and not self.state.stream_ready:
                self.state.set_stream_ready()
                print(f"Stream ready! Batch {self.state.batches_processed}/{self.state.total_batches_expected}")
                print(f"Estimated time remaining: {estimated_time_remaining:.1f}s, Audio length: {self.audio_length:.1f}s")
                print(f"Frames in queue: {self.frame_queue.qsize()}")
    
    def _print_batch_progress(self, current_batch):
        """Print batch progress for debugging"""
        if current_batch % 2 == 0:  # Print every 2nd batch to avoid spam
            elapsed_time = time.time() - self.state.inference_start_time
            if elapsed_time > 0:
                estimated_remaining = (self.state.total_batches_expected / (self.state.batches_processed / elapsed_time)) - elapsed_time
                print(f"Batch {current_batch}/{self.state.total_batches_expected} completed, frames in queue: {self.frame_queue.qsize()}, time remaining: {estimated_remaining:.1f}s")
            else:
                print(f"Batch {current_batch}/{self.state.total_batches_expected} completed, frames in queue: {self.frame_queue.qsize()}")
    
    def get_frame_from_queue(self):
        """Get a frame from the queue with timeout"""
        try:
            frame = self.frame_queue.get(timeout=0.1)
            return frame
        except queue.Empty:
            # Log when queue is empty
            if self.state.inference_complete:
                print("Queue empty and inference complete")
            else:
                print(f"Queue empty, inference still running. Queue size: {self.frame_queue.qsize()}")
            return None
    
    async def mjpeg_response(self):
        """Generate MJPEG response for streaming"""
        boundary = "frame"
        frame_delay = 1.0 / self.initial_fps
        start_time = asyncio.get_event_loop().time()
        frame_count = 0
        
        print("Starting MJPEG stream...")
        print(f"Queue size at start: {self.frame_queue.qsize()}")
        print(f"Audio length: {self.audio_length}s, FPS: {self.initial_fps}")
        print(f"Frame delay: {frame_delay:.3f}s (targeting {1/frame_delay:.1f} FPS)")
        print(f"Stream ready: {self.state.stream_ready}, Inference complete: {self.state.inference_complete}")
        
        while True:
            # Get frame from queue
            frame = self.get_frame_from_queue()
            
            # Check for end of stream signal (None frame)
            if frame is None:
                if self.state.inference_complete:
                    print("End of stream signal received, finishing stream")
                    self._log_stream_completion()
                    break
                else:
                    # No frame available but inference still running, wait
                    await asyncio.sleep(0.01)
                    continue
            
            frame_count += 1
            if frame_count % 10 == 0:  # Log every 10th frame to reduce spam
                current_time = asyncio.get_event_loop().time()
                elapsed = current_time - start_time
                actual_fps = frame_count / elapsed if elapsed > 0 else 0
                print(f"Streaming frame {frame_count}, queue size: {self.frame_queue.qsize()}, actual FPS: {actual_fps:.1f}")
            
            # Calculate when this frame should be displayed based on FPS
            target_time = start_time + (frame_count * frame_delay)
            current_time = asyncio.get_event_loop().time()
            
            # Wait if we're ahead of schedule to maintain proper frame rate
            if current_time < target_time:
                await asyncio.sleep(target_time - current_time)
            else:
                # If we're behind schedule, log it but don't skip frames
                if frame_count % 30 == 0:  # Log every 30th frame to avoid spam
                    delay = current_time - target_time
                    print(f"Frame {frame_count} delayed by {delay:.3f}s")
            
            # Convert numpy frame to JPEG
            ret, jpeg = cv2.imencode('.jpg', frame)
            if not ret:
                print(f"Failed to encode frame {frame_count}")
                continue
                
            frame_data = (b"--" + boundary.encode() + b"\r\n"
                   b"Content-Type: image/jpeg\r\n"
                   b"Content-Length: " + str(len(jpeg)).encode() + b"\r\n\r\n" + jpeg.tobytes() + b"\r\n")
            
            if frame_count % 10 == 0:  # Log every 10th frame to reduce spam
                print(f"Yielding frame {frame_count}, size: {len(jpeg)} bytes")
            yield frame_data
    
    def _log_stream_completion(self):
        """Log stream completion with timing information"""
        stream_end_time = time.time()
        if self.state.inference_end_time is not None:
            streaming_duration = stream_end_time - self.state.inference_end_time
            print(f"Streaming finished. Time from inference end to stream end: {streaming_duration:.2f} seconds")
        else:
            print("Streaming finished (inference end time not available)") 