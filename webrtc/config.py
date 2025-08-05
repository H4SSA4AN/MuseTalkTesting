"""
Configuration file for MuseTalk streaming server
"""

# Avatar Configuration
AVATAR_CONFIG = {
    "avatar_id": "1FrameAvatar",
    "video_path": "data/video/1FrameVideo.mp4",
    "bbox_shift": 0,
    "batch_size": 4,
    "preparation": False,
    "extra_margin": 10,
    "parsing_mode": "jaw",
    "left_cheek_width": 90,
    "right_cheek_width": 90,
    "audio_padding_length_left": 2,
    "audio_padding_length_right": 2,
    "skip_save_images": True,
    "fps": 25,
    "gpu_id": 0,
    "vae_type": "sd-vae",
    "unet_config": "./models/musetalk/musetalk.json",
    "unet_model_path": "./models/musetalk/pytorch_model.bin",
    "whisper_dir": "./models/whisper",
    "ffmpeg_path": "./ffmpeg-4.4-amd64-static/"
}

# Audio Configuration
AUDIO_CONFIG = {
    "audio_path": "data/audio/RealTimeAudioTest.wav",
    "default_duration": 15.0  # seconds
}

# Streaming Configuration
STREAMING_CONFIG = {
    "frame_buffer_size": 1000,
    "stream_delay": 1000,  # ms before starting stream
    "status_check_interval": 500,  # ms between status checks
    "video_width": 1280,
    "video_height": 720
}

# Server Configuration
SERVER_CONFIG = {
    "host": "localhost",
    "port": 8080
} 