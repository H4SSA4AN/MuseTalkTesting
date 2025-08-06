"""
Avatar management for MuseTalk streaming server
"""

import sys
import os
import librosa
from scripts.realtime_inference import Avatar
from config import AVATAR_CONFIG, AUDIO_CONFIG


class AvatarManager:
    """Manages avatar initialization and configuration"""
    
    def __init__(self):
        self.avatar = None
        self.avatar_fps = AVATAR_CONFIG["fps"]
        self.audio_length = AUDIO_CONFIG["default_duration"]
        self.ready = False
    
    def initialize(self):
        """Initialize the avatar with all required components"""
        print("Pre-initializing MuseTalk avatar...")
        
        try:
            # Create and initialize the avatar
            self.avatar = Avatar(**AVATAR_CONFIG)
            
            # Update fps value
            self.avatar_fps = self.avatar.fps
            print(f"Avatar FPS set to: {self.avatar_fps}")
            
            # Get audio length
            self._load_audio_length()
            
            print("Avatar pre-initialization complete!")
            self.ready = True
            
        except Exception as e:
            print(f"Error pre-initializing avatar: {e}")
            self.ready = False
    
    def _load_audio_length(self):
        """Load audio file length"""
        try:
            self.audio_length = librosa.get_duration(path=AUDIO_CONFIG["audio_path"])
            print(f"Audio length: {self.audio_length} seconds")
        except Exception as e:
            print(f"Could not determine audio length, defaulting to {AUDIO_CONFIG['default_duration']}s. Error: {e}")
            self.audio_length = AUDIO_CONFIG["default_duration"]
    
    def is_ready(self) -> bool:
        """Check if avatar is ready for inference"""
        return self.ready and self.avatar is not None
    
    def get_avatar(self):
        """Get the initialized avatar instance"""
        return self.avatar
    
    def get_fps(self) -> int:
        """Get avatar FPS"""
        return self.avatar_fps
    
    def get_audio_length(self) -> float:
        """Get audio length in seconds"""
        return self.audio_length
    
    def get_audio_path(self) -> str:
        """Get audio file path"""
        return AUDIO_CONFIG["audio_path"] 