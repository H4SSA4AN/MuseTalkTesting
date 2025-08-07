# Troubleshooting Streaming Issues

This guide helps diagnose and fix common streaming problems in the separated MuseTalk architecture.

## Prerequisites Check

### Environment Requirements
Before troubleshooting, ensure the MuseTestEnv environment is properly set up:

```bash
# Check if MuseTestEnv exists
conda env list | grep MuseTestEnv

# If not found, create it
conda env create -f environment.yml

# Activate the environment
conda activate MuseTestEnv
```

## Common Streaming Issues

### 1. **No Frames Appearing in Browser**

**Symptoms:**
- Video player shows but no frames appear
- Browser console shows connection errors
- Stream status shows "ready" but no video

**Possible Causes:**
- Frame buffer is empty
- Inference not processing frames correctly
- Streaming handler not yielding frames properly
- Web server proxy not forwarding stream correctly
- MuseTalk server not running in MuseTestEnv environment

**Solutions:**
1. Check MuseTalk server logs for frame processing messages
2. Verify inference is running: `curl http://localhost:8081/stream_status`
3. Check if frames are being added to buffer
4. Test direct connection to MuseTalk server stream
5. Ensure MuseTalk server is running in MuseTestEnv environment

### 2. **Stream Starts Then Stops**

**Symptoms:**
- Video plays for a few seconds then stops
- Browser shows "connection lost" errors
- Server logs show inference completion

**Possible Causes:**
- Inference completes before streaming finishes
- Frame buffer runs out of frames
- Network timeout issues
- Browser buffer underrun

**Solutions:**
1. Check inference duration vs audio length
2. Increase frame buffer size in config
3. Verify streaming timing logic
4. Check browser network tab for errors

### 3. **Slow or Choppy Streaming**

**Symptoms:**
- Video plays but is choppy or slow
- Frames appear to skip
- Audio/video sync issues

**Possible Causes:**
- Frame processing too slow
- Network bandwidth issues
- Browser performance problems
- Incorrect FPS settings

**Solutions:**
1. Check frame processing rate in logs
2. Reduce video quality/resolution
3. Check system resources (CPU/GPU)
4. Verify FPS settings match avatar configuration

### 4. **Connection Refused Errors**

**Symptoms:**
- Browser shows "connection refused"
- Server logs show connection errors
- Port already in use errors

**Possible Causes:**
- Server not running
- Wrong port configuration
- Firewall blocking connections
- Previous process still running

**Solutions:**
1. Check if servers are running: `netstat -ano | findstr :808`
2. Kill any existing processes on ports 8080/8081
3. Verify firewall settings
4. Check server startup logs

### 5. **Environment-Related Issues**

**Symptoms:**
- "MuseTestEnv environment not found"
- Import errors in MuseTalk server
- "conda not found" errors
- Missing dependencies

**Possible Causes:**
- MuseTestEnv environment not created
- Environment not activated
- Conda not in PATH
- Missing dependencies in environment

**Solutions:**
1. Create MuseTestEnv environment: `conda env create -f environment.yml`
2. Activate environment: `conda activate MuseTestEnv`
3. Check conda installation and PATH
4. Install missing dependencies: `pip install -r requirements.txt`

## Debugging Steps

### Step 1: Check Environment and Server Status
```bash
# Check if MuseTestEnv exists
conda env list | grep MuseTestEnv

# Check if servers are running
netstat -ano | findstr :808

# Test MuseTalk server directly
curl http://localhost:8081/stream_status

# Test web server proxy
curl http://localhost:8080/stream_status
```

### Step 2: Check Server Logs
Look for these key messages in server logs:

**MuseTalk Server:**
- "Pre-initializing MuseTalk avatar..."
- "Avatar pre-initialization complete!"
- "Starting inference with X frames..."
- "Stream ready! Batch X/Y"
- "Starting MJPEG stream..."

**Web Server:**
- "Web interface server starting..."
- "Connecting to MuseTalk server at..."
- "Proxying stream from MuseTalk server..."

### Step 3: Test Individual Components
```bash
# Run the test script
python test_servers.py

# Test direct streaming
curl -N http://localhost:8081/stream

# Test MuseTalk server in environment
conda run -n MuseTestEnv python musetalkServer/server.py
```

### Step 4: Check Browser Console
Open browser developer tools and check:
- Network tab for failed requests
- Console tab for JavaScript errors
- Performance tab for timing issues

## Configuration Checks

### Frame Buffer Size
In `musetalkServer/config.py`:
```python
STREAMING_CONFIG = {
    "frame_buffer_size": 1000,  # Increase if frames are dropping
    # ...
}
```

### Server Ports
Verify ports are correct and not conflicting:
- Web server: 8080
- MuseTalk server: 8081

### Audio/Video Sync
Check timing configuration:
```python
AUDIO_CONFIG = {
    "default_duration": 15.0  # Should match actual audio length
}
```

### Environment Configuration
Ensure MuseTestEnv has all required dependencies:
```bash
conda activate MuseTestEnv
pip list | grep -E "(torch|opencv|librosa|aiohttp)"
```

## Performance Optimization

### For Better Streaming Performance:

1. **Reduce Frame Buffer Size** if memory is limited
2. **Increase Frame Buffer Size** if frames are dropping
3. **Adjust FPS** to match system capabilities
4. **Use Lower Resolution** for testing
5. **Check GPU Memory** usage during inference

### System Requirements:
- **RAM**: At least 8GB available
- **GPU**: 4GB+ VRAM for inference
- **CPU**: Multi-core for frame processing
- **Network**: Stable local connection
- **Conda**: Properly installed and in PATH

## Emergency Recovery

If streaming completely fails:

1. **Kill all processes:**
   ```bash
   taskkill /F /IM python.exe
   ```

2. **Clear any cached data:**
   ```bash
   # Clear browser cache
   # Restart servers
   ```

3. **Restart servers in order:**
   ```bash
   # Terminal 1: Start MuseTalk server in environment
   conda activate MuseTestEnv
   python musetalkServer/server.py
   
   # Terminal 2: Start web server
   python webrtc/server.py
   ```

4. **Test with minimal configuration:**
   - Use shorter audio file
   - Reduce video resolution
   - Disable audio temporarily

## Environment-Specific Issues

### Windows Issues
- **Conda not found**: Add conda to PATH or use full path
- **Permission errors**: Run as administrator
- **Path issues**: Use forward slashes or escape backslashes

### Linux/Mac Issues
- **Source activate**: Use `conda run -n MuseTestEnv` instead
- **Permission denied**: Check file permissions
- **Library not found**: Install system dependencies

## Getting Help

If issues persist:

1. **Collect logs** from both servers
2. **Note exact error messages** from browser
3. **Check system resources** (CPU, RAM, GPU)
4. **Test with different browsers**
5. **Verify all dependencies** are installed
6. **Check environment status**: `conda info`

## Common Error Messages

- **"Failed to connect to MuseTalk server"**: Check if MuseTalk server is running in MuseTestEnv
- **"Stream not available"**: Check inference status and frame buffer
- **"Avatar not ready"**: Wait for avatar initialization to complete
- **"Inference already started"**: Wait for current inference to complete or restart servers
- **"MuseTestEnv environment not found"**: Create environment with `conda env create -f environment.yml`
- **"Import error"**: Activate MuseTestEnv environment before running MuseTalk server
