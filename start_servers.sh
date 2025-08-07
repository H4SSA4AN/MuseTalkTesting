#!/bin/bash

echo "Starting MuseTalk with separated servers..."
echo ""

# Load environment variables from .env file if it exists
if [ -f .env ]; then
    echo "Loading environment variables from .env file..."
    export $(grep -v '^#' .env | xargs)
    echo "Environment variables loaded successfully"
else
    echo "No .env file found, using default configuration"
fi

# Get port numbers from environment or use defaults
MUSETALK_PORT=${MUSETALK_PORT:-8081}
WEB_PORT=${WEB_PORT:-8080}
MUSETALK_HOST=${MUSETALK_HOST:-localhost}
WEB_HOST=${WEB_HOST:-localhost}

echo "MuseTalk inference server will run on $MUSETALK_HOST:$MUSETALK_PORT (in MuseTestEnv)"
echo "Web interface server will run on $WEB_HOST:$WEB_PORT"
echo ""
echo "Press Ctrl+C to stop both servers"
echo ""

# Check if MuseTestEnv exists
if conda env list | grep -q "MuseTestEnv"; then
    echo "✓ MuseTestEnv environment found"
else
    echo "✗ MuseTestEnv environment not found!"
    echo "Please create the environment first:"
    echo "conda env create -f environment.yml"
    exit 1
fi

echo "Starting servers..."
echo ""

# Start MuseTalk server in MuseTestEnv environment in background
echo "Starting MuseTalk server in MuseTestEnv environment..."
conda run -n MuseTestEnv python musetalkServer/server.py &
MUSETALK_PID=$!

# Wait for MuseTalk server to initialize
echo "Waiting for MuseTalk server to initialize..."
sleep 5

# Start web server
echo "Starting web interface server..."
python3 webrtc/server.py

# Cleanup: kill MuseTalk server when web server exits
kill $MUSETALK_PID 2>/dev/null
