# MuseTalk with Separated Servers

This project has been refactored to separate the web interface and MuseTalk inference into two distinct servers for better modularity and maintainability.

## Prerequisites

### Required Environment
The MuseTalk inference server requires the **MuseTestEnv** conda environment to run properly.

**Create the environment:**
```bash
conda env create -f environment.yml
```

**Activate the environment:**
```bash
conda activate MuseTestEnv
```

## Architecture

### 1. Web Interface Server (`webrtc/`)
- **Port**: 8080
- **Purpose**: Serves the web interface and handles client requests
- **Environment**: Can run in any Python environment
- **Components**:
  - `server.py` - Main web server with proxy endpoints
  - `config.py` - Configuration for web interface
  - `templates/index.html` - Web interface template
  - `public/` - Static assets

### 2. MuseTalk Inference Server (`musetalkServer/`)
- **Port**: 8081
- **Purpose**: Handles all MuseTalk inference and streaming logic
- **Environment**: **Requires MuseTestEnv conda environment**
- **Components**:
  - `server.py` - Main inference server
  - `config.py` - Avatar and inference configuration
  - `state_manager.py` - Inference state management
  - `avatar_manager.py` - Avatar initialization and management
  - `inference_handler.py` - Frame processing and inference logic
  - `streaming_handler.py` - MJPEG streaming functionality

## File Structure

```
├── webrtc/                    # Web interface server
│   ├── server.py             # Web server with proxy endpoints
│   ├── config.py             # Web interface configuration
│   ├── templates/
│   │   └── index.html        # Web interface template
│   └── public/               # Static assets
├── musetalkServer/           # MuseTalk inference server
│   ├── server.py             # Main inference server
│   ├── config.py             # Avatar and inference config
│   ├── state_manager.py      # State management
│   ├── avatar_manager.py     # Avatar management
│   ├── inference_handler.py  # Inference logic
│   └── streaming_handler.py  # Streaming functionality
├── start_servers.py          # Startup script for both servers
├── start_servers.bat         # Windows batch file
├── start_servers.sh          # Unix/Linux shell script
├── run_musetalk_server.py    # Dedicated MuseTalk server launcher
├── run_musetalk_server.bat   # Windows MuseTalk server launcher
└── README_SEPARATED_SERVERS.md
```

## Running the Application

### Option 1: Use the startup script (Recommended)
```bash
python start_servers.py
```

This will:
1. Check if MuseTestEnv environment exists
2. Start MuseTalk inference server on port 8081 (in MuseTestEnv)
3. Start web interface server on port 8080

### Option 2: Use platform-specific scripts

**Windows:**
```bash
start_servers.bat
```

**Unix/Linux:**
```bash
./start_servers.sh
```

### Option 3: Run servers separately

**Terminal 1 - MuseTalk Inference Server (in MuseTestEnv):**
```bash
# Windows
run_musetalk_server.bat

# Unix/Linux
conda run -n MuseTestEnv python musetalkServer/server.py

# Or use the Python launcher
python run_musetalk_server.py
```

**Terminal 2 - Web Interface Server:**
```bash
cd webrtc
python server.py
```

## Environment Management

### Checking Environment Status
```bash
# List all conda environments
conda env list

# Check if MuseTestEnv exists
conda env list | grep MuseTestEnv
```

### Creating the Environment
If the MuseTestEnv environment doesn't exist:
```bash
# Create from environment.yml
conda env create -f environment.yml

# Or create manually
conda create -n MuseTestEnv python=3.8
conda activate MuseTestEnv
pip install -r requirements.txt
```

### Activating the Environment
```bash
conda activate MuseTestEnv
```

## Accessing the Application

1. Open your web browser
2. Navigate to `http://localhost:8080`
3. Click "Start Inference" to begin the MuseTalk process

## Configuration

### Web Interface Configuration (`webrtc/config.py`)
- `WEB_SERVER_CONFIG`: Web server host and port
- `MUSETALK_SERVER_CONFIG`: MuseTalk server connection details
- `CLIENT_CONFIG`: Client-side configuration

### MuseTalk Server Configuration (`musetalkServer/config.py`)
- `AVATAR_CONFIG`: Avatar model configuration
- `AUDIO_CONFIG`: Audio file settings
- `STREAMING_CONFIG`: Streaming parameters
- `SERVER_CONFIG`: Server host and port

## Benefits of Separation

1. **Modularity**: Each server has a single responsibility
2. **Scalability**: Servers can be deployed on different machines
3. **Maintainability**: Easier to debug and modify individual components
4. **Resource Management**: Better control over resource allocation
5. **Development**: Independent development and testing of components
6. **Environment Isolation**: MuseTalk dependencies are isolated in MuseTestEnv

## API Endpoints

### Web Interface Server (Port 8080)
- `GET /` - Serve web interface
- `GET /start` - Proxy to MuseTalk server start endpoint
- `GET /audio` - Proxy to MuseTalk server audio endpoint
- `GET /stream_status` - Proxy to MuseTalk server status endpoint
- `GET /stream` - Proxy to MuseTalk server stream endpoint

### MuseTalk Server (Port 8081)
- `GET /start` - Start inference process
- `GET /audio` - Serve audio file
- `GET /stream_status` - Get streaming status
- `GET /stream` - MJPEG video stream

## Troubleshooting

### Common Issues

1. **Port conflicts**: Ensure ports 8080 and 8081 are available
2. **Connection errors**: Check that both servers are running
3. **Avatar initialization**: Verify model files are in the correct locations
4. **Audio file**: Ensure the audio file exists in the specified path
5. **Environment issues**: Make sure MuseTestEnv is properly set up

### Environment Troubleshooting

**"MuseTestEnv environment not found"**
```bash
# Check if environment exists
conda env list

# Create environment if missing
conda env create -f environment.yml
```

**"conda not found"**
- Make sure conda is installed and in your PATH
- Try using the full path to conda

**"Import errors in MuseTalk server"**
- Make sure you're running in the MuseTestEnv environment
- Check that all dependencies are installed: `pip list`

### Logs

- MuseTalk server logs will show inference progress and avatar initialization
- Web server logs will show proxy requests and connection status

## Development

To modify the application:

1. **Web Interface**: Edit files in the `webrtc/` directory
2. **Inference Logic**: Edit files in the `musetalkServer/` directory
3. **Configuration**: Update the respective `config.py` files

Each server can be developed and tested independently.

### Development Environment Setup

**For Web Interface Development:**
```bash
cd webrtc
python server.py
```

**For MuseTalk Development:**
```bash
conda activate MuseTestEnv
cd musetalkServer
python server.py
```
