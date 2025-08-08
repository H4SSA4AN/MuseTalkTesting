# Audio Recording Feature

This document describes the new audio recording functionality added to the MuseTalk web interface.

## Features

### 1. Audio Recording
- **Record Button**: Click "Start Recording" to begin recording audio from your microphone
- **Stop Recording**: Click "Stop Recording" to stop and save the recording
- **Visual Feedback**: The button changes color and text to indicate recording status
- **Status Messages**: Real-time status updates show recording progress and save confirmation

### 2. Recording Management
- **Automatic Naming**: Recordings are automatically named with timestamps (e.g., `recording_20241208_131500.wav`)
- **Storage**: All recordings are saved to the `recordings/` folder
- **View Recordings**: Click "View Recordings" to see all saved recordings with playback controls

### 3. File Organization
- **Directory**: `recordings/` folder is automatically created if it doesn't exist
- **Format**: All recordings are saved as WAV files
- **Metadata**: Each recording includes creation time and file size information

## How to Use

1. **Start the Web Server**:
   ```bash
   cd webrtc
   python server.py
   ```

2. **Access the Web Interface**:
   - Open your browser and go to `http://localhost:8080`
   - Grant microphone permissions when prompted

3. **Record Audio**:
   - Click "Start Recording" to begin
   - Speak into your microphone
   - Click "Stop Recording" when finished
   - The recording will be automatically saved

4. **View Recordings**:
   - Click "View Recordings" to see all saved recordings
   - Each recording includes an audio player for playback
   - Recordings are sorted by creation time (newest first)

## Technical Details

### Frontend (JavaScript)
- Uses the MediaRecorder API for browser-based audio recording
- Handles microphone permissions and stream management
- Provides real-time UI feedback during recording
- Uploads recordings via FormData to the server

### Backend (Python/aiohttp)
- **`/save_recording`**: POST endpoint to save uploaded audio files
- **`/list_recordings`**: GET endpoint to retrieve list of saved recordings
- **`/recordings/{filename}`**: GET endpoint to serve individual recording files
- Automatic directory creation and file management
- Security checks to prevent directory traversal attacks

### File Structure
```
recordings/
├── recording_20241208_131500.wav
├── recording_20241208_131523.wav
└── ...
```

## Browser Compatibility

The recording feature requires a modern browser that supports:
- MediaRecorder API
- getUserMedia API
- File API
- Fetch API

Compatible browsers include:
- Chrome 47+
- Firefox 25+
- Safari 14.1+
- Edge 79+

## Security Considerations

- Recordings are stored locally in the `recordings/` directory
- File serving includes path traversal protection
- Only WAV files are accepted and served
- Automatic cleanup of temporary files

## Troubleshooting

### Microphone Access Issues
- Ensure your browser has permission to access the microphone
- Check that your microphone is properly connected and working
- Try refreshing the page and granting permissions again

### Recording Not Saving
- Check that the `recordings/` directory exists and is writable
- Verify the web server has proper permissions
- Check browser console for error messages

### Playback Issues
- Ensure the recording file was saved successfully
- Check that the audio format is supported by your browser
- Try downloading the file and playing it locally
