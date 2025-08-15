"""
Streaming handler for MuseTalk frame processing and MJPEG streaming
"""

import asyncio
import cv2
import numpy as np
import time
import math
from musetalk.utils.blending import get_image_blending
from typing import List, Optional
import torch
try:
    from .state_manager import StreamingState
    from .avatar_manager import AvatarManager
except ImportError:
    # Fallback for direct script execution
    from state_manager import StreamingState
    from avatar_manager import AvatarManager


class StreamingHandler:
    """Handles frame processing and MJPEG streaming"""
    
    def __init__(self, state: StreamingState, avatar_manager: AvatarManager):
        self.state = state
        self.avatar_manager = avatar_manager
        self.avatar = avatar_manager.get_avatar()
    
    def _process_frame_batch(self, frames_batch: List[np.ndarray]) -> List[np.ndarray]:
        """Processes a batch of raw frames (blending, etc.)."""
        processed_frames = []
        for frame in frames_batch:
            idx = self.state.get_buffer_size() + len(processed_frames) # Use a simple index for cycling
            bbox = self.avatar.coord_list_cycle[idx % len(self.avatar.coord_list_cycle)]
            ori_frame = np.copy(self.avatar.frame_list_cycle[idx % len(self.avatar.frame_list_cycle)])
            
            if isinstance(bbox, torch.Tensor):
                bbox = bbox.tolist()
            x1, y1, x2, y2 = bbox
            
            try:
                res_frame = cv2.resize(frame.astype(np.uint8), (x2 - x1, y2 - y1))
            except Exception:
                continue

            mask = self.avatar.mask_list_cycle[idx % len(self.avatar.mask_list_cycle)]
            mask_crop_box = self.avatar.mask_coords_list_cycle[idx % len(self.avatar.mask_coords_list_cycle)]
            
            blended_frame = get_image_blending(ori_frame, res_frame, bbox, mask, mask_crop_box)
            processed_frames.append(blended_frame)
        return processed_frames

    async def _add_frames_to_buffer_async(self, frames: List[np.ndarray]):
        """Asynchronously add a batch of frames to the buffer and set stream ready."""
        for frame in frames:
            self.state.add_frame_to_buffer(frame)

    def _check_stream_ready(self):
        """Check if stream should be ready to start"""
        elapsed_time = time.time() - self.state.inference_start_time
        if elapsed_time > 0 and self.state.batches_processed > 0:
            processing_rate = self.state.batches_processed / elapsed_time
            self.state.estimated_inference_time = self.state.total_batches_expected / processing_rate
            estimated_time_remaining = self.state.estimated_inference_time - elapsed_time
            
            # Start streaming when estimated time remaining equals audio length
            if estimated_time_remaining <= self.state.audio_length and not self.state.stream_ready:
                self.state.set_stream_ready()
                print(f"Stream ready! Batch {self.state.batches_processed}/{self.state.total_batches_expected}")
                print(f"Estimated time remaining: {estimated_time_remaining:.1f}s, Audio length: {self.state.audio_length:.1f}s")
    
    def _print_batch_progress(self, current_batch: int, total_batches: int, start_time: float):
        """Print batch progress with ETA"""
        if total_batches == 0:
            return
            
        elapsed_time = time.time() - start_time
        avg_time_per_batch = elapsed_time / current_batch if current_batch > 0 else 0
        remaining_batches = total_batches - current_batch
        eta = remaining_batches * avg_time_per_batch
        
        # Get dynamic audio length from state
        audio_len = self.state.audio_length
        fps = self.avatar_manager.get_fps()
        
        print(
            f"Processed batch {current_batch}/{total_batches} | "
            f"ETA: {eta:.2f}s | "
            f"Buffer: {self.state.get_buffer_size()} | "
            f"Audio Len: {audio_len:.2f}s | "
            f"FPS: {fps}"
        )
    
    async def mjpeg_response(self):
        """Generate MJPEG response - send entire buffer first, then new frames"""
        boundary = "frame"
        frame_count = 0
        
        print(f"[MJPEG] Starting MJPEG response. Initial buffer size: {self.state.get_buffer_size()}")
        
        try:
            # Phase 1: Send entire initial buffer as quickly as possible
            initial_buffer_size = self.state.get_buffer_size()
            if initial_buffer_size > 0:
                print(f"[MJPEG] Sending entire initial buffer ({initial_buffer_size} frames)")
                
                # Send all frames in buffer immediately
                while self.state.get_buffer_size() > 0:
                    frame = self.state.get_frame_from_buffer()
                    if frame is not None:
                        frame_count += 1
                        
                        # Convert numpy frame to JPEG
                        ret, jpeg = cv2.imencode('.jpg', frame)
                        if not ret:
                            continue
                        
                        # Create the MJPEG chunk
                        chunk = (b"--" + boundary.encode() + b"\r\n"
                                b"Content-Type: image/jpeg\r\n"
                                b"Content-Length: " + str(len(jpeg)).encode() + b"\r\n\r\n" + jpeg.tobytes() + b"\r\n")
                        
                        yield chunk
                
                print(f"[MJPEG] Initial buffer sent. Frame count: {frame_count}")
                print(f"[MJPEG] Buffer size after sending: {self.state.get_buffer_size()}")
            
            # Phase 2: Wait for new frames and serve them as they arrive
            print(f"[MJPEG] Starting Phase 2 - waiting for new frames")
            while True:
                # Wait for new frames to be available
                wait_count = 0
                while self.state.get_buffer_size() == 0 and not self.state.inference_complete:
                    await asyncio.sleep(0.01)
                    wait_count += 1
                    if wait_count % 1000 == 0:  # Print every 10 seconds
                        print(f"[MJPEG] Waiting for new frames... buffer_size={self.state.get_buffer_size()}, inference_complete={self.state.inference_complete}")
                
                # Get new frame from buffer
                frame = self.state.get_frame_from_buffer()
                if frame is None:
                    # Check if inference is complete and no more frames
                    if self.state.inference_complete:
                        print(f"[MJPEG] Inference complete, no more frames. Total frame count: {frame_count}")
                        break
                    else:
                        # Still waiting for frames, continue
                        continue
                
                frame_count += 1
                
                # Convert numpy frame to JPEG
                ret, jpeg = cv2.imencode('.jpg', frame)
                if not ret:
                    continue
                
                # Create the MJPEG chunk
                chunk = (b"--" + boundary.encode() + b"\r\n"
                        b"Content-Type: image/jpeg\r\n"
                        b"Content-Length: " + str(len(jpeg)).encode() + b"\r\n\r\n" + jpeg.tobytes() + b"\r\n")
                
                yield chunk
                
                # If inference is complete and we've processed all frames, break
                if self.state.inference_complete and self.state.get_buffer_size() == 0:
                    print(f"[MJPEG] All frames processed, ending stream. Total frame count: {frame_count}")
                    break
                
        except Exception as e:
            print(f"[MJPEG] Error during streaming: {e}")
            import traceback
            traceback.print_exc()
        finally:
            # Only yield final boundary when inference is truly complete
            if self.state.inference_complete:
                try:
                    yield b"--" + boundary.encode() + b"\r\n\r\n"
                    print(f"[MJPEG] Stream ended. Total frames: {frame_count}")
                except:
                    pass
    
    def _log_stream_completion(self):
        """Log stream completion with timing information"""
        stream_end_time = time.time()
        if self.state.inference_end_time is not None:
            streaming_duration = stream_end_time - self.state.inference_end_time
            print(f"Streaming finished. Time from inference end to stream end: {streaming_duration:.2f} seconds")
        else:
            print("Streaming finished (inference end time not available)") 