"""
Refactored MuseTalk streaming server
"""

import sys
import os
import asyncio
import threading
from aiohttp import web

# Add parent directory to path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Import our modular components
from config import STREAMING_CONFIG, SERVER_CONFIG
from state_manager import StreamingState
from avatar_manager import AvatarManager
from streaming_handler import StreamingHandler

# Initialize global components
state = StreamingState(frame_buffer_size=STREAMING_CONFIG["frame_buffer_size"])
avatar_manager = AvatarManager()
streaming_handler = None

routes = web.RouteTableDef()


@routes.get("/")
async def index(request):
    """Serve the main HTML page"""
    try:
        with open("webrtc/templates/index.html", "r") as f:
            html_content = f.read()
        return web.Response(text=html_content, content_type="text/html")
    except FileNotFoundError:
        return web.Response(text="Template file not found", status=404)


@routes.get("/start")
async def start_inference(request):
    """Start the inference process"""
    global state, avatar_manager, streaming_handler
    
    if state.inference_triggered:
        return web.json_response({"success": False, "error": "Inference already started"})
    
    if not avatar_manager.is_ready():
        return web.json_response({"success": False, "error": "Avatar not ready. Please wait for initialization to complete."})
    
    # Reset state for new inference
    state.reset_inference_state()
    state.start_inference()
    
    # Initialize streaming handler
    streaming_handler = StreamingHandler(state, avatar_manager)
    
    # Get the current event loop
    loop = asyncio.get_event_loop()
    
    # Start the inference in a background thread
    def start_inference_thread():
        print("Starting inference with pre-initialized avatar...")
        
        # Create custom process_frames function
        custom_process_frames = streaming_handler.create_custom_process_frames(loop)
        
        # Get avatar instance
        avatar = avatar_manager.get_avatar()
        
        # Replace the process_frames method temporarily
        original_process_frames = avatar.process_frames
        avatar.process_frames = custom_process_frames
        
        # Run the full inference pipeline
        avatar.inference(
            avatar_manager.get_audio_path(), 
            None, 
            avatar.fps, 
            avatar.skip_save_images
        )
        
        # Restore original method
        avatar.process_frames = original_process_frames
    
    threading.Thread(target=start_inference_thread, daemon=True).start()
    
    return web.json_response({"success": True, "message": "Inference started"})


@routes.get("/audio")
async def serve_audio(request):
    """Serve the audio file for playback"""
    audio_path = avatar_manager.get_audio_path()
    try:
        with open(audio_path, 'rb') as f:
            audio_data = f.read()
        return web.Response(body=audio_data, headers={
            'Content-Type': 'audio/wav',
            'Content-Length': str(len(audio_data))
        })
    except FileNotFoundError:
        return web.Response(text="Audio file not found", status=404)


@routes.get("/stream_status")
async def stream_status(request):
    """Check if streaming is ready to start"""
    return web.json_response({
        "stream_ready": state.stream_ready,
        "inference_complete": state.inference_complete
    })


@routes.get("/stream")
async def stream(request):
    """Handle MJPEG streaming"""
    global state, streaming_handler
    
    if not state.streaming_started:
        return web.Response(text="Inference not started", status=400)

    # Wait until stream is ready
    while not state.stream_ready and not state.inference_complete:
        await asyncio.sleep(0.1)
    
    print(f"beginning stream (audio length: {avatar_manager.get_audio_length()}s)")

    return web.Response(
        body=streaming_handler.mjpeg_response(), 
        status=200, 
        headers={"Content-Type": "multipart/x-mixed-replace; boundary=frame"}
    )


def initialize_server():
    """Initialize the server components"""
    print("Initializing MuseTalk streaming server...")
    
    # Initialize avatar
    avatar_manager.initialize()
    
    if not avatar_manager.is_ready():
        print("Failed to initialize avatar. Server cannot start.")
        return False
    
    print("Server initialization complete!")
    return True


def main():
    """Main server entry point"""
    # Initialize server components
    if not initialize_server():
        sys.exit(1)
    
    # Create and configure the web application
    app = web.Application()
    app.add_routes(routes)
    
    # Start the server
    print(f"Server starting with pre-initialized avatar...")
    print(f"Server will be available at: http://{SERVER_CONFIG['host']}:{SERVER_CONFIG['port']}")
    
    web.run_app(app, host=SERVER_CONFIG["host"], port=SERVER_CONFIG["port"])


if __name__ == "__main__":
    main() 