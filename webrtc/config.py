"""
Configuration file for MuseTalk web interface
"""

import os

# MuseTalk Server Configuration with environment variable support
MUSETALK_SERVER_CONFIG = {
    "host": os.getenv("MUSETALK_HOST", "localhost"),
    "port": int(os.getenv("MUSETALK_PORT", "8081"))  # Can be overridden with MUSETALK_PORT env var
}

# Web Server Configuration with environment variable support
WEB_SERVER_CONFIG = {
    "host": os.getenv("WEB_HOST", "localhost"),
    "port": int(os.getenv("WEB_PORT", "8080"))  # Can be overridden with WEB_PORT env var
}

# Client Configuration
CLIENT_CONFIG = {
    "musetalk_server_url": f"http://{MUSETALK_SERVER_CONFIG['host']}:{MUSETALK_SERVER_CONFIG['port']}",
    "video_width": 1280,
    "video_height": 720,
    "status_check_interval": 500  # ms between status checks
} 