import os
import pathlib
import platform
import threading
import time
import asyncio
from typing import Optional, Callable, List
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class FileHandler:
    """Improved file handler with Linux compatibility and better error handling."""
    
    def __init__(self, base_dir: str, answers_dir_name: str = "answers"):
        self.base_dir = pathlib.Path(base_dir)
        self.answers_dir = self.base_dir / answers_dir_name
        self._ensure_directory_permissions()
        
    def _ensure_directory_permissions(self):
        """Ensure the answers directory exists with proper permissions."""
        try:
            self.answers_dir.mkdir(parents=True, exist_ok=True)
            # Set permissions to 755 (rwxr-xr-x)
            self.answers_dir.chmod(0o755)
            logger.info(f"Created/verified answers directory: {self.answers_dir}")
        except PermissionError as e:
            logger.error(f"Permission denied creating directory {self.answers_dir}: {e}")
            raise
        except Exception as e:
            logger.error(f"Error creating directory {self.answers_dir}: {e}")
            raise
            
    def check_permissions(self) -> bool:
        """Check if we have proper permissions to read/write in the answers directory."""
        try:
            # Test write permission
            test_file = self.answers_dir / ".test_write"
            test_file.write_text("test")
            test_file.unlink()
            
            # Test read permission
            os.listdir(self.answers_dir)
            
            logger.info("Directory permissions verified successfully")
            return True
        except PermissionError as e:
            logger.error(f"Permission check failed: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error during permission check: {e}")
            return False
            
    def save_audio_file(self, audio_data: bytes, filename: Optional[str] = None) -> pathlib.Path:
        """Save audio file with proper error handling and permissions."""
        if filename is None:
            filename = f"Answer_{int(time.time()*1000)}.wav"
            
        file_path = self.answers_dir / filename
        
        try:
            # Write file atomically
            temp_path = file_path.with_suffix(file_path.suffix + '.tmp')
            temp_path.write_bytes(audio_data)
            
            # Set proper permissions (644: rw-r--r--)
            temp_path.chmod(0o644)
            
            # Atomic move
            temp_path.rename(file_path)
            
            logger.info(f"Successfully saved audio file: {file_path}")
            return file_path
            
        except PermissionError as e:
            logger.error(f"Permission denied saving file {file_path}: {e}")
            raise
        except Exception as e:
            logger.error(f"Error saving file {file_path}: {e}")
            # Clean up temp file if it exists
            if temp_path.exists():
                try:
                    temp_path.unlink()
                except:
                    pass
            raise
            
    def get_audio_files(self) -> List[pathlib.Path]:
        """Get all audio files in the answers directory."""
        try:
            audio_files = [
                f for f in self.answers_dir.iterdir() 
                if f.is_file() and f.suffix.lower() in ['.wav', '.mp3', '.flac']
            ]
            return sorted(audio_files, key=lambda f: f.stat().st_mtime)
        except PermissionError as e:
            logger.error(f"Permission denied reading directory {self.answers_dir}: {e}")
            return []
        except Exception as e:
            logger.error(f"Error reading directory {self.answers_dir}: {e}")
            return []
            
    def clear_directory(self):
        """Clear all files in the answers directory."""
        try:
            for file_path in self.answers_dir.iterdir():
                if file_path.is_file():
                    file_path.unlink()
                elif file_path.is_dir():
                    import shutil
                    shutil.rmtree(file_path)
            logger.info(f"Cleared answers directory: {self.answers_dir}")
        except PermissionError as e:
            logger.error(f"Permission denied clearing directory {self.answers_dir}: {e}")
            raise
        except Exception as e:
            logger.error(f"Error clearing directory {self.answers_dir}: {e}")
            raise


class FileWatcher:
    """Cross-platform file watcher with Linux optimization."""
    
    def __init__(self, directory: pathlib.Path, callback: Callable[[pathlib.Path], None]):
        self.directory = directory
        self.callback = callback
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._is_linux = platform.system() == "Linux"
        
    def start(self):
        """Start the file watcher."""
        if self._is_linux:
            self._start_linux_watcher()
        else:
            self._start_polling_watcher()
            
    def stop(self):
        """Stop the file watcher."""
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
            
    def _start_linux_watcher(self):
        """Start Linux-specific inotify watcher."""
        try:
            import pyinotify
            
            class EventHandler(pyinotify.ProcessEvent):
                def __init__(self, callback):
                    super().__init__()
                    self.callback = callback
                    
                def process_IN_CREATE(self, event):
                    if event.pathname.endswith(('.wav', '.mp3', '.flac')):
                        self.callback(pathlib.Path(event.pathname))
                        
                def process_IN_MOVED_TO(self, event):
                    if event.pathname.endswith(('.wav', '.mp3', '.flac')):
                        self.callback(pathlib.Path(event.pathname))
            
            wm = pyinotify.WatchManager()
            handler = EventHandler(self.callback)
            notifier = pyinotify.Notifier(wm, handler)
            
            wm.add_watch(str(self.directory), pyinotify.IN_CREATE | pyinotify.IN_MOVED_TO)
            
            def run_notifier():
                while not self._stop_event.is_set():
                    try:
                        notifier.process_events()
                        if notifier.check_events():
                            notifier.read_events()
                    except Exception as e:
                        logger.error(f"inotify error: {e}")
                        time.sleep(1.0)
                        
            self._thread = threading.Thread(target=run_notifier, daemon=True)
            self._thread.start()
            logger.info(f"Started Linux inotify watcher for {self.directory}")
            
        except ImportError:
            logger.warning("pyinotify not available, falling back to polling")
            self._start_polling_watcher()
        except Exception as e:
            logger.error(f"Failed to start inotify watcher: {e}, falling back to polling")
            self._start_polling_watcher()
            
    def _start_polling_watcher(self):
        """Start cross-platform polling watcher."""
        def poll_files():
            last_seen = None
            last_mtime = 0.0
            
            while not self._stop_event.is_set():
                try:
                    files = [
                        f for f in self.directory.iterdir() 
                        if f.is_file() and f.suffix.lower() in ['.wav', '.mp3', '.flac']
                    ]
                    
                    if files:
                        newest = max(files, key=lambda f: f.stat().st_mtime)
                        mtime = newest.stat().st_mtime
                        
                        if newest != last_seen or mtime > last_mtime:
                            last_seen = newest
                            last_mtime = mtime
                            self.callback(newest)
                            
                except Exception as e:
                    logger.error(f"Polling watcher error: {e}")
                    
                time.sleep(0.3)  # Poll every 300ms
                
        self._thread = threading.Thread(target=poll_files, daemon=True)
        self._thread.start()
        logger.info(f"Started polling watcher for {self.directory}")
