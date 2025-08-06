"""
Configuration for Web Server (Client Side)
"""

# Inference Server Configuration
INFERENCE_SERVER_CONFIG = {
    "url": "http://192.168.1.100:8080",  # Change this to your inference machine's IP
    "timeout": 30,
    "retry_attempts": 3
}

# Web Server Configuration
WEB_SERVER_CONFIG = {
    "host": "0.0.0.0",  # Allow external connections
    "port": 3000,
    "debug": False
}