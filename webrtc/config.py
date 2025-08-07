"""
Configuration file for MuseTalk web interface
"""

# MuseTalk Server Configuration
MUSETALK_SERVER_CONFIG = {
    "host": "localhost",
    "port": 8081  # MuseTalk inference server port
}

# Web Server Configuration
WEB_SERVER_CONFIG = {
    "host": "localhost",
    "port": 8080  # Web interface server port
}

# Client Configuration
CLIENT_CONFIG = {
    "musetalk_server_url": f"http://{MUSETALK_SERVER_CONFIG['host']}:{MUSETALK_SERVER_CONFIG['port']}",
    "video_width": 1280,
    "video_height": 720,
    "status_check_interval": 500  # ms between status checks
} 