"""
State management for MuseTalk streaming server
"""

from collections import deque
from dataclasses import dataclass, field
from typing import Optional
import time


@dataclass
class StreamingState:
    """Manages the state of the streaming system"""
    
    # Frame buffer
    frame_buffer_size: int
    frame_buffer: deque = field(init=False)
    
    # Streaming flags
    streaming_started: bool = False
    inference_complete: bool = False
    inference_triggered: bool = False
    stream_ready: bool = False
    
    # Batch tracking
    batches_processed: int = 0
    total_batches_expected: int = 0
    estimated_inference_time: float = 0
    
    # Timing
    inference_start_time: Optional[float] = None
    inference_end_time: Optional[float] = None
    
    # Avatar settings
    avatar_fps: int = 25
    audio_length: float = 0
    
    # Avatar instance
    pre_initialized_avatar: Optional[object] = None
    avatar_ready: bool = False
    
    def __post_init__(self):
        self.frame_buffer = deque(maxlen=self.frame_buffer_size)
    
    def reset_inference_state(self):
        """Reset inference-related state for a new run"""
        self.batches_processed = 0
        self.total_batches_expected = 0
        self.estimated_inference_time = 0
        self.inference_start_time = None
        self.inference_end_time = None
        self.inference_complete = False
        self.stream_ready = False
        self.streaming_started = False
        self.inference_triggered = False
        self.frame_buffer.clear()
    
    def start_inference(self):
        """Mark inference as started"""
        self.inference_triggered = True
        self.streaming_started = True
        self.inference_start_time = time.time()
    
    def complete_inference(self):
        """Mark inference as complete"""
        self.inference_complete = True
        self.inference_end_time = time.time()
    
    def set_stream_ready(self):
        """Mark stream as ready to start"""
        self.stream_ready = True
    
    def add_frame_to_buffer(self, frame):
        """Add a frame to the buffer"""
        self.frame_buffer.append(frame)
    
    def get_buffer_size(self) -> int:
        """Get current buffer size"""
        return len(self.frame_buffer)
    
    def get_frame_from_buffer(self):
        """Get and remove a frame from the buffer"""
        if self.frame_buffer:
            return self.frame_buffer.popleft()
        return None
    
    def get_inference_duration(self) -> float:
        """Get total inference duration"""
        if self.inference_start_time and self.inference_end_time:
            return self.inference_end_time - self.inference_start_time
        return 0.0
    
    def get_streaming_duration(self) -> float:
        """Get streaming duration (from inference end to now)"""
        if self.inference_end_time:
            return time.time() - self.inference_end_time
        return 0.0 