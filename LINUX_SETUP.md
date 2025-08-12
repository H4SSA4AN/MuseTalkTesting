# MuseTalk Linux Setup and File Handling Improvements

This document describes the improvements made to ensure MuseTalk runs properly on Linux systems, particularly addressing audio file transfer issues between the omni server and muse server.

## Overview of Improvements

### 1. Enhanced File Handling
- **Cross-platform path handling** using `pathlib`
- **Proper file permissions** management (755 for directories, 644 for files)
- **Atomic file operations** to prevent corruption
- **Better error handling** with specific error messages

### 2. Improved File Watching
- **Linux-optimized file watching** using `inotify` when available
- **Fallback to polling** for cross-platform compatibility
- **Real-time file detection** for better audio file transfer reliability

### 3. Permission Management
- **Automatic permission verification** on startup
- **Directory creation with proper permissions**
- **Error handling for permission issues**

## Installation

### Quick Setup (Linux)
```bash
# Make setup script executable
chmod +x setup_linux.sh

# Run the setup script
./setup_linux.sh
```

### Manual Setup
1. **Install system dependencies:**
   ```bash
   # Ubuntu/Debian
   sudo apt-get update
   sudo apt-get install -y ffmpeg inotify-tools python3 python3-pip python3-venv
   
   # CentOS/RHEL
   sudo yum install -y ffmpeg inotify-tools python3 python3-pip
   
   # Fedora
   sudo dnf install -y ffmpeg inotify-tools python3 python3-pip
   ```

2. **Create virtual environment:**
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```

3. **Install Python dependencies:**
   ```bash
   pip install --upgrade pip
   pip install -r requirements.txt
   ```

4. **Create necessary directories:**
   ```bash
   mkdir -p answers results models
   chmod 755 answers results models
   ```

## File Handling Improvements

### New FileHandler Class
The `FileHandler` class provides:
- **Automatic directory creation** with proper permissions
- **Atomic file saving** to prevent corruption
- **Permission verification** on startup
- **Cross-platform path handling**

### New FileWatcher Class
The `FileWatcher` class provides:
- **Linux inotify support** for real-time file detection
- **Cross-platform polling fallback**
- **Thread-safe callbacks** for file detection

### Usage Example
```python
from musetalk.utils.file_handler import FileHandler, FileWatcher

# Initialize file handler
file_handler = FileHandler("/path/to/base/dir", "answers")

# Save audio file
file_path = file_handler.save_audio_file(audio_data, "answer.wav")

# Set up file watcher
def on_new_file(file_path):
    print(f"New file detected: {file_path}")

watcher = FileWatcher(file_handler.answers_dir, on_new_file)
watcher.start()
```

## Troubleshooting

### Common Issues

1. **Permission Denied Errors**
   ```bash
   # Check directory permissions
   ls -la answers/
   
   # Fix permissions if needed
   chmod 755 answers/
   chmod 644 answers/*.wav
   ```

2. **File Not Found Errors**
   ```bash
   # Verify file exists
   ls -la answers/
   
   # Check file permissions
   file answers/Answer.wav
   ```

3. **File Watching Not Working**
   ```bash
   # Test file watching
   python test_file_handling.py
   
   # Check if inotify is available
   which inotifywait
   ```

### Testing File Handling
```bash
# Run the test suite
python test_file_handling.py
```

### Health Check Endpoint
The server now provides a health check endpoint:
```bash
curl http://localhost:8090/health
```

Response includes:
- `status`: Server status
- `have_answer`: Whether an audio file is available
- `answers_dir`: Path to answers directory
- `permissions_ok`: Whether permissions are correct

## Audio File Transfer Process

### Improved Upload Process
1. **File validation** - Check file format and size
2. **Atomic write** - Write to temporary file first
3. **Permission setting** - Set proper file permissions (644)
4. **Atomic move** - Move to final location
5. **Event signaling** - Notify watchers of new file

### File Detection
1. **Real-time detection** - Using inotify on Linux
2. **Fallback polling** - Every 300ms if inotify unavailable
3. **Thread-safe callbacks** - Proper async event handling

## Configuration

### Environment Variables
```bash
# Set custom answers directory
export MUSETALK_ANSWERS_DIR="/custom/path/answers"

# Set custom permissions
export MUSETALK_DIR_PERMS="755"
export MUSETALK_FILE_PERMS="644"
```

### Server Configuration
The server automatically:
- Creates necessary directories
- Sets proper permissions
- Verifies file system access
- Starts optimized file watchers

## Performance Improvements

### Linux Optimizations
- **inotify file watching** - Real-time file detection
- **Atomic file operations** - Prevents file corruption
- **Efficient path handling** - Using pathlib for better performance

### Cross-Platform Compatibility
- **Fallback mechanisms** - Works on all platforms
- **Graceful degradation** - Polling if inotify unavailable
- **Error recovery** - Automatic retry mechanisms

## Monitoring and Logging

### Log Levels
- **INFO** - Normal operations
- **WARNING** - Non-critical issues
- **ERROR** - Critical issues requiring attention

### Key Log Messages
```
[MuseTalk] Created/verified answers directory: /path/to/answers
[MuseTalk] Successfully saved audio file: /path/to/answers/Answer.wav
[MuseTalk] Detected new answer file: /path/to/answers/Answer.wav
[MuseTalk] File watcher started on /path/to/answers
```

## Security Considerations

### File Permissions
- **Directories**: 755 (rwxr-xr-x)
- **Audio files**: 644 (rw-r--r--)
- **Temporary files**: Automatically cleaned up

### Path Validation
- **Absolute path resolution** - Prevents path traversal
- **File type validation** - Only audio files accepted
- **Size limits** - Configurable file size limits

## Support

For issues related to:
- **File handling**: Check `test_file_handling.py`
- **Permissions**: Run `ls -la answers/`
- **File watching**: Check `inotifywait` availability
- **Server startup**: Check health endpoint

## Migration from Previous Version

If upgrading from a previous version:
1. **Backup existing files** - Save any important audio files
2. **Run setup script** - `./setup_linux.sh`
3. **Test functionality** - `python test_file_handling.py`
4. **Verify permissions** - Check directory permissions
5. **Start server** - `./start_server.sh`
