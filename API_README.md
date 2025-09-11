# MuseTalk Service API Documentation

This document provides detailed information about the MuseTalk Service API endpoints, including request syntax, parameters, and response formats.

## Base URL

The service runs on port 8085 by default:
```
http://localhost:8085
```

## Endpoints

### 1. Health Check

**Endpoint:** `GET /health`

**Description:** Checks if the service is running and models are loaded.

**Request:**
```bash
curl -X GET http://localhost:8085/health
```

**Response:**
```json
{
  "status": "healthy",
  "models_loaded": true
}
```

**Response Fields:**
- `status`: Service status ("healthy" or "unhealthy")
- `models_loaded`: Boolean indicating if all models are loaded

**Status Codes:**
- `200 OK`: Service is healthy
- `500 Internal Server Error`: Service is not healthy

---

### 2. Process Audio

**Endpoint:** `POST /process`

**Description:** Processes an audio file with a video and streams generated frames to a specified URL.

**Request:**
```bash
curl -X POST http://localhost:8085/process \
  -F "audio=@path/to/audio.wav" \
  -F "video_path=data/video/yongen.mp4" \
  -F "stream_url=http://localhost:5001/receive_frame" \
  -F "bbox_shift=0"
```

**Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `audio` | File | Yes | Audio file (WAV, MP3, etc.) |
| `video_path` | String | Yes | Path to the video file |
| `stream_url` | String | Yes | URL to stream frames to |
| `bbox_shift` | Integer | No | Bounding box shift value (default: 0) |

**Request Details:**
- Content-Type: `multipart/form-data`
- Audio file should be a valid audio format (WAV, MP3, etc.)
- Video path should be relative to the service working directory
- Stream URL should be accessible from the service

**Success Response:**
```json
{
  "status": "processing_started",
  "message": "Audio processing started in background"
}
```

**Error Response:**
```json
{
  "error": "No audio file provided"
}
```

**Response Fields:**
- `status`: Processing status ("processing_started" or "error")
- `message`: Status message or error message

**Status Codes:**
- `200 OK`: Processing started successfully (runs in background)
- `400 Bad Request`: Invalid request parameters
- `500 Internal Server Error`: Processing failed

**Processing Flow:**
1. Audio file is uploaded and saved to `inputs/` folder (overwrites any existing file)
2. Processing starts in background thread (API returns immediately)
3. `realtime.yaml` configuration is loaded for inference parameters
4. Video frames are extracted and processed
5. Audio features are extracted using Whisper
6. Inference is performed in separate thread using realtime.yaml configuration
7. Frames are streamed to the specified URL in real-time
8. Audio file remains in inputs folder until next upload

---

### 3. Get Status

**Endpoint:** `GET /status`

**Description:** Returns the current processing status and queue information.

**Request:**
```bash
curl -X GET http://localhost:8085/status
```

**Response:**
```json
{
  "status": "idle",
  "queue_size": 0
}
```

**Response Fields:**
- `status`: Current processing status ("idle", "processing", or "not_initialized")
- `queue_size`: Number of frames waiting in the streaming queue

**Status Codes:**
- `200 OK`: Status retrieved successfully

**Status Values:**
- `idle`: Service is ready to process requests
- `processing`: Currently processing an audio file
- `not_initialized`: Service has not been initialized

---

## Error Handling

### Common Error Responses

**Missing Audio File:**
```json
{
  "error": "No audio file provided"
}
```

**Missing Required Parameters:**
```json
{
  "error": "video_path and stream_url are required"
}
```

**Service Not Initialized:**
```json
{
  "error": "Service not initialized"
}
```

**File Not Found:**
```json
{
  "error": "Video file not found: data/video/yongen.mp4"
}
```

**Processing Error:**
```json
{
  "error": "Failed to extract audio features"
}
```

### HTTP Status Codes

| Code | Description |
|------|-------------|
| 200 | Success |
| 400 | Bad Request (invalid parameters) |
| 500 | Internal Server Error |

---

## Frame Streaming Protocol

When processing audio, the service streams frames to the specified URL using the following protocol:

**Frame Endpoint:** The URL specified in `stream_url` parameter

**Request Method:** `POST`

**Headers:**
- `Content-Type: image/jpeg`
- `Frame-Index: <frame_number>`

**Body:** JPEG-encoded frame data

**Example Frame Request:**
```bash
POST http://localhost:5001/receive_frame
Content-Type: image/jpeg
Frame-Index: 0

<JPEG frame data>
```

**Expected Response:**
```json
{
  "status": "received",
  "frame_index": 0
}
```

---

## Usage Examples

### Python Example

```python
import requests

# Health check
response = requests.get('http://localhost:8085/health')
print(response.json())

# Process audio
with open('audio.wav', 'rb') as audio_file:
    files = {'audio': audio_file}
    data = {
        'video_path': 'data/video/yongen.mp4',
        'stream_url': 'http://localhost:5001/receive_frame',
        'bbox_shift': 0
    }
    
    response = requests.post('http://localhost:8085/process', 
                           files=files, data=data)
    print(response.json())
```

### JavaScript Example

```javascript
// Health check
fetch('http://localhost:8085/health')
  .then(response => response.json())
  .then(data => console.log(data));

// Process audio
const formData = new FormData();
formData.append('audio', audioFile);
formData.append('video_path', 'data/video/yongen.mp4');
formData.append('stream_url', 'http://localhost:5001/receive_frame');
formData.append('bbox_shift', '0');

fetch('http://localhost:8085/process', {
    method: 'POST',
    body: formData
})
.then(response => response.json())
.then(data => console.log(data));
```

### cURL Examples

**Health Check:**
```bash
curl -X GET http://localhost:8085/health
```

**Get Status:**
```bash
curl -X GET http://localhost:8085/status
```

**Process Audio:**
```bash
curl -X POST http://localhost:8085/process \
  -F "audio=@audio.wav" \
  -F "video_path=data/video/yongen.mp4" \
  -F "stream_url=http://localhost:5001/receive_frame" \
  -F "bbox_shift=0"
```

---

## Configuration

The service uses the `configs/inference/realtime.yaml` configuration file and follows the realtime inference pipeline. Key features:

### Model Configuration
- **UNet Model**: `./models/musetalk/pytorch_model.bin`
- **UNet Config**: `./models/musetalk/musetalk.json`
- **Whisper Model**: `./models/whisper`
- **VAE Type**: `sd-vae`

### Processing Settings
- **Version**: v15 (optimized for realtime inference)
- **Precision**: Half-precision (FP16) for faster processing
- **Batch Size**: 20 (optimized for realtime)
- **FPS**: 25 (default, or from video file)
- **Face Parsing**: Jaw mode with cheek width 90
- **Audio Padding**: 2 frames on left and right
- **Extra Margin**: 10 pixels for face cropping
- **Threading**: Inference runs in separate thread to avoid blocking API
- **Configuration**: Uses `realtime.yaml` for inference parameters

### Audio Input Storage
- **Input Folder**: `inputs/` (created automatically)
- **File Naming**: `{original_name}.{extension}` (no timestamp)
- **Single File Policy**: Only one audio file at a time - new files overwrite previous ones

---

## Troubleshooting

### Common Issues

1. **Service Not Responding:**
   - Check if service is running: `curl http://localhost:8085/health`
   - Verify port 8085 is not blocked by firewall

2. **Model Loading Errors:**
   - Ensure model files are downloaded
   - Check paths in configuration file
   - Verify sufficient disk space

3. **Processing Failures:**
   - Check audio file format (WAV recommended)
   - Verify video file exists and is accessible
   - Ensure stream URL is reachable

4. **Memory Issues:**
   - Reduce batch_size in configuration
   - Use shorter audio files
   - Close other applications using GPU

### Debug Mode

Enable debug mode for detailed logging:
```bash
python musetalk_service.py --debug
```

### Testing

Use the provided test scripts:
```bash
# Test service connectivity
python test_service.py

# Test configuration
python test_config.py

# Check paths
python check_paths.py
```

---

## Rate Limiting

Currently, the service processes one request at a time. Multiple concurrent requests will be queued.

## Security Considerations

- The service accepts file uploads - validate file types
- Stream URLs should be from trusted sources
- Consider implementing authentication for production use
- Monitor disk usage for temporary files

---

## Version Information

- **Service Version:** 1.0.0
- **MuseTalk Version:** v15
- **API Version:** v1

For more information, see the main [SERVICE_README.md](SERVICE_README.md).
