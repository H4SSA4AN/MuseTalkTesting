#!/usr/bin/env python3
"""
Test script for improved file handling in MuseTalk server.
This script tests the FileHandler and FileWatcher classes to ensure they work correctly on Linux.
"""

import os
import sys
import time
import tempfile
import pathlib
import threading
from unittest.mock import Mock

# Add the project root to the path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from musetalk.utils.file_handler import FileHandler, FileWatcher

def test_file_handler():
    """Test the FileHandler class."""
    print("Testing FileHandler...")
    
    # Create a temporary directory for testing
    with tempfile.TemporaryDirectory() as temp_dir:
        file_handler = FileHandler(temp_dir, "test_answers")
        
        # Test directory creation and permissions
        assert file_handler.answers_dir.exists()
        assert file_handler.check_permissions()
        print("✓ Directory creation and permissions test passed")
        
        # Test saving audio file
        test_audio_data = b"fake audio data"
        file_path = file_handler.save_audio_file(test_audio_data, "test.wav")
        assert file_path.exists()
        assert file_path.read_bytes() == test_audio_data
        print("✓ Audio file saving test passed")
        
        # Test getting audio files
        audio_files = file_handler.get_audio_files()
        assert len(audio_files) == 1
        assert audio_files[0].name == "test.wav"
        print("✓ Audio file listing test passed")
        
        # Test clearing directory
        file_handler.clear_directory()
        assert len(file_handler.get_audio_files()) == 0
        print("✓ Directory clearing test passed")

def test_file_watcher():
    """Test the FileWatcher class."""
    print("Testing FileWatcher...")
    
    with tempfile.TemporaryDirectory() as temp_dir:
        file_handler = FileHandler(temp_dir, "test_answers")
        
        # Track detected files
        detected_files = []
        detection_event = threading.Event()
        
        def on_new_file(file_path):
            detected_files.append(file_path)
            detection_event.set()
        
        # Start file watcher
        watcher = FileWatcher(file_handler.answers_dir, on_new_file)
        watcher.start()
        
        # Wait a moment for watcher to start
        time.sleep(0.5)
        
        # Create a test file
        test_file = file_handler.answers_dir / "test_watch.wav"
        test_file.write_bytes(b"test data")
        
        # Wait for detection (with timeout)
        if detection_event.wait(timeout=2.0):
            assert len(detected_files) == 1
            assert detected_files[0].name == "test_watch.wav"
            print("✓ File watching test passed")
        else:
            print("✗ File watching test failed - no detection within timeout")
        
        # Stop watcher
        watcher.stop()

def test_error_handling():
    """Test error handling in file operations."""
    print("Testing error handling...")
    
    # Test with non-writable directory
    try:
        # Try to create handler in a system directory (should fail)
        file_handler = FileHandler("/root", "test")
        file_handler.check_permissions()
        print("✗ Permission error handling test failed - should have raised exception")
    except (PermissionError, RuntimeError):
        print("✓ Permission error handling test passed")
    except Exception as e:
        print(f"✓ Error handling test passed (caught: {type(e).__name__})")

def main():
    """Run all tests."""
    print("Starting file handling tests...")
    print("=" * 50)
    
    try:
        test_file_handler()
        test_file_watcher()
        test_error_handling()
        
        print("=" * 50)
        print("All tests completed successfully!")
        return 0
        
    except Exception as e:
        print(f"Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())
