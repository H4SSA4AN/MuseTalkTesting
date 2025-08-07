"""
MuseTalk inference server
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
from state_manager import InferenceState
from avatar_manager import AvatarManager
from inference_handler import InferenceHandler
from streaming_handler import StreamingHandler

# Initialize global components
state = InferenceState(frame_buffer_size=STREAMING_CONFIG["frame_buffer_size"])
avatar_manager = AvatarManager()
inference_handler = None
streaming_handler = None

routes = web.RouteTableDef()


@routes.get("/start")
async def start_inference(request):
    """Start the inference process"""
    global state, avatar_manager, inference_handler, streaming_handler
    
    # Check if we can start a new inference
    if state.inference_triggered and not state.inference_complete:
        return web.json_response({"success": False, "error": "Inference already in progress"})
    
    if not avatar_manager.is_ready():
        return web.json_response({"success": False, "error": "Avatar not ready. Please wait for initialization to complete."})
    
    # Reset state for new inference
    state.reset_all_state()
    state.start_inference()
    
    # Initialize handlers
    inference_handler = InferenceHandler(state, avatar_manager)
    streaming_handler = StreamingHandler(state, avatar_manager)
    
    # Get the current event loop
    loop = asyncio.get_event_loop()
    
    # Start the inference in a background thread
    def start_inference_thread():
        print("Starting inference with pre-initialized avatar...")
        
        # Create custom process_frames function
        custom_process_frames = inference_handler.create_custom_process_frames(loop)
        
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
        
        print("Inference thread completed")
    
    threading.Thread(target=start_inference_thread, daemon=True).start()
    
    return web.json_response({"success": True, "message": "Inference started"})


@routes.get("/reset")
async def reset_inference(request):
    """Reset the inference state to allow starting again"""
    global state
    
    print("Manual reset requested")
    state.reset_all_state()
    
    return web.json_response({"success": True, "message": "State reset complete"})


@routes.get("/get_settings")
async def get_settings(request):
    """Get current fps and batch size settings"""
    global avatar_manager
    
    try:
        avatar = avatar_manager.get_avatar()
        if avatar:
            return web.json_response({
                "success": True,
                "fps": avatar.fps,
                "batch_size": avatar.batch_size
            })
        else:
            return web.json_response({
                "success": True,
                "fps": 25,  # Default values
                "batch_size": 4
            })
    except Exception as e:
        return web.json_response({"success": False, "error": str(e)})


@routes.post("/update_settings")
async def update_settings(request):
    """Update fps and batch size settings"""
    global avatar_manager
    
    try:
        data = await request.json()
        fps = data.get('fps', 25)
        batch_size = data.get('batch_size', 4)
        
        # Validate input
        if not (1 <= fps <= 60):
            return web.json_response({"success": False, "error": "FPS must be between 1 and 60"})
        
        if not (1 <= batch_size <= 16):
            return web.json_response({"success": False, "error": "Batch size must be between 1 and 16"})
        
        # Update avatar settings if available
        avatar = avatar_manager.get_avatar()
        if avatar:
            avatar.fps = fps
            avatar.batch_size = batch_size
            # Also update the avatar manager's FPS tracking
            avatar_manager.update_fps(fps)
            print(f"Updated settings: FPS={fps}, Batch Size={batch_size}")
        
        return web.json_response({"success": True, "message": "Settings updated successfully"})
    except Exception as e:
        return web.json_response({"success": False, "error": str(e)})


@routes.get("/status")
async def get_status(request):
    """Get detailed status of the inference system"""
    global state
    
    return web.json_response({
        "inference_triggered": state.inference_triggered,
        "inference_complete": state.inference_complete,
        "stream_ready": state.stream_ready,
        "batches_processed": state.batches_processed,
        "total_batches_expected": state.total_batches_expected,
        "frames_in_buffer": state.get_buffer_size(),
        "ready_for_new_inference": state.is_ready_for_new_inference(),
        "inference_duration": state.get_inference_duration()
    })


@routes.get("/audio")
async def serve_audio(request):
    """Serve the audio file for playback"""
    audio_path = avatar_manager.get_audio_path()
    print(f"Audio request received, serving: {audio_path}")
    
    try:
        with open(audio_path, 'rb') as f:
            audio_data = f.read()
        print(f"Audio file loaded: {len(audio_data)} bytes")
        return web.Response(body=audio_data, headers={
            'Content-Type': 'audio/wav',
            'Content-Length': str(len(audio_data)),
            'Cache-Control': 'no-cache'  # Prevent caching
        })
    except FileNotFoundError:
        print(f"Audio file not found: {audio_path}")
        return web.Response(text="Audio file not found", status=404)
    except Exception as e:
        print(f"Error serving audio: {e}")
        return web.Response(text=f"Error serving audio: {str(e)}", status=500)


@routes.get("/stream_status")
async def stream_status(request):
    """Check if streaming is ready to start"""
    response_data = {
        "stream_ready": state.stream_ready,
        "inference_complete": state.inference_complete,
        "inference_triggered": state.inference_triggered,
        "ready_for_new_inference": state.is_ready_for_new_inference(),
        "batches_processed": state.batches_processed,
        "total_batches_expected": state.total_batches_expected,
        "frames_in_buffer": state.get_buffer_size()
    }
    
    # Add debug logging for inference completion
    if state.inference_complete:
        print(f"Stream status: Inference complete - {response_data}")
    
    return web.json_response(response_data)


@routes.get("/stream")
async def stream(request):
    """Handle MJPEG streaming"""
    global state, streaming_handler
    
    if not state.inference_triggered:
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
    print("Initializing MuseTalk inference server...")
    
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
