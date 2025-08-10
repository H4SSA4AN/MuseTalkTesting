#!/usr/bin/env python3
"""
Simple script to run the MuseTalk server with Mini-Omni URL
"""

import sys
import os

# Add the webrtc directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'webrtc'))

if __name__ == "__main__":
    # Import and run the server
    from server_refactored import main
    main()
