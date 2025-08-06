"""
Inference Server for MuseTalk - Server Side
This runs on the machine with GPU and handles the actual inference
"""

import sys
import os
import asyncio
import threading
from aiohttp import web
from aiohttp_cors import setup as cors_setup, ResourceOptions

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

@routes.post("/start")
async def start_inference(request):
    """Start the inference process with custom FPS and batch size"""
    global state, avatar_manager, streaming_handler
    
    if state.inference_triggered:
        return web.json_response({"success": False, "error": "Inference already started"})
    
    if not avatar_manager.is_ready():
        return web.json_response({"success": False, "error": "Avatar not ready. Please wait for initialization to complete."})
    
    try:
        # Get FPS and batch size from request body
        body = await request.json()
        fps = body.get('fps', 25)
        batch_size = body.get('batch_size', 4)
        
        print(f"Received inference start request with FPS: {fps}, Batch Size: {batch_size}")
        
        # Ensure state is completely reset for new inference
        print(f"Before reset - streaming_started: {state.streaming_started}, inference_triggered: {state.inference_triggered}, stream_ready: {state.stream_ready}")
        state.reset_inference_state()
        print(f"After reset - streaming_started: {state.streaming_started}, inference_triggered: {state.inference_triggered}, stream_ready: {state.stream_ready}")
        
        # Wait a moment to ensure any background reset tasks are complete
        await asyncio.sleep(0.1)
        
        # Mark inference as started
        state.start_inference()
        print(f"After start_inference - streaming_started: {state.streaming_started}, inference_triggered: {state.inference_triggered}, stream_ready: {state.stream_ready}")
        
        # Create new streaming handler for this inference run
        streaming_handler = StreamingHandler(state, avatar_manager, initial_fps=fps)
        
        # Clear any existing frame queue
        if streaming_handler.frame_queue:
            while not streaming_handler.frame_queue.empty():
                try:
                    streaming_handler.frame_queue.get_nowait()
                except:
                    break
        
        # Get the current event loop
        loop = asyncio.get_event_loop()
        
        # Start the inference in a background thread
        def start_inference_thread():
            print(f"Starting inference with FPS: {fps}, Batch Size: {batch_size}")
            
            # Create custom process_frames function
            custom_process_frames = streaming_handler.create_custom_process_frames(loop)
            
            # Get avatar instance
            avatar = avatar_manager.get_avatar()
            
            # Update avatar batch size with new value
            original_batch_size = avatar.batch_size
            avatar.batch_size = batch_size
            
            # Replace the process_frames method temporarily
            original_process_frames = avatar.process_frames
            avatar.process_frames = custom_process_frames
            
            # Run the full inference pipeline
            avatar.inference(
                avatar_manager.get_audio_path(), 
                None, 
                fps,  # Use the new FPS
                avatar.skip_save_images
            )
            
            # Restore original method and settings
            avatar.process_frames = original_process_frames
            avatar.batch_size = original_batch_size
        
        threading.Thread(target=start_inference_thread, daemon=True).start()
        
        return web.json_response({"success": True, "message": f"Inference started with FPS: {fps}, Batch Size: {batch_size}"})
        
    except Exception as e:
        return web.json_response({"success": False, "error": f"Failed to start inference: {str(e)}"})

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

@routes.get("/server_status")
async def server_status(request):
    """Check server status"""
    status = "listening"
    if state.inference_triggered:
        if not state.inference_complete:
            status = "inference_running"
        else:
            status = "ready_for_next"
    
    return web.json_response({
        "server_ready": avatar_manager.is_ready(),
        "inference_triggered": state.inference_triggered,
        "inference_complete": state.inference_complete,
        "stream_ready": state.stream_ready,
        "streaming_started": state.streaming_started,
        "status": status
    })

@routes.get("/debug_state")
async def debug_state(request):
    """Debug endpoint to check all state variables"""
    return web.json_response({
        "inference_triggered": state.inference_triggered,
        "inference_complete": state.inference_complete,
        "streaming_started": state.streaming_started,
        "stream_ready": state.stream_ready,
        "batches_processed": state.batches_processed,
        "total_batches_expected": state.total_batches_expected,
        "inference_start_time": state.inference_start_time,
        "inference_end_time": state.inference_end_time,
        "avatar_ready": avatar_manager.is_ready(),
        "streaming_handler_exists": streaming_handler is not None,
        "frame_queue_size": streaming_handler.frame_queue.qsize() if streaming_handler else 0
    })

@routes.get("/reset_state")
async def reset_state(request):
    """Manually reset the state (for debugging)"""
    global state, streaming_handler
    
    state.reset_inference_state()
    
    if streaming_handler and streaming_handler.frame_queue:
        while not streaming_handler.frame_queue.empty():
            try:
                streaming_handler.frame_queue.get_nowait()
            except:
                break
    
    return web.json_response({"success": True, "message": "State reset"})

@routes.get("/stream_status")
async def stream_status(request):
    """Check if streaming is ready to start"""
    return web.json_response({
        "stream_ready": state.stream_ready,
        "inference_complete": state.inference_complete,
        "inference_triggered": state.inference_triggered,
        "streaming_started": state.streaming_started
    })

@routes.get("/stream")
async def stream(request):
    """Handle MJPEG streaming"""
    global state, streaming_handler
    
    if not state.streaming_started:
        return web.Response(text="Inference not started", status=400)

    # Wait until stream is ready or inference is complete
    print(f"Waiting for stream to be ready... (stream_ready: {state.stream_ready}, inference_complete: {state.inference_complete})")
    print(f"Current state - streaming_started: {state.streaming_started}, inference_triggered: {state.inference_triggered}")
    
    wait_count = 0
    while not state.stream_ready and not state.inference_complete:
        await asyncio.sleep(0.1)
        wait_count += 1
        if wait_count % 50 == 0:  # Log every 5 seconds
            print(f"Still waiting... (stream_ready: {state.stream_ready}, inference_complete: {state.inference_complete}, wait_count: {wait_count})")
    
    print(f"Stream ready check complete after {wait_count} iterations")
    print(f"Final state - stream_ready: {state.stream_ready}, inference_complete: {state.inference_complete}")

    print(f"beginning stream (audio length: {avatar_manager.get_audio_length()}s)")
    print(f"Queue size before streaming: {streaming_handler.frame_queue.qsize()}")

    # Create the streaming response using the async generator directly
    response = web.StreamResponse(
        status=200,
        headers={"Content-Type": "multipart/x-mixed-replace; boundary=frame"}
    )
    
    # Start the response
    await response.prepare(request)
    
    # Stream frames directly
    async for frame_data in streaming_handler.mjpeg_response():
        await response.write(frame_data)
    
    await response.write_eof()
    
    # Reset state after streaming is complete
    print("Streaming complete, resetting state for next inference...")
    state.reset_inference_state()
    
    # Clear the frame queue for next inference
    if streaming_handler and streaming_handler.frame_queue:
        while not streaming_handler.frame_queue.empty():
            try:
                streaming_handler.frame_queue.get_nowait()
            except:
                break
    
    print("State reset complete, ready for next inference")
    return response

def initialize_server():
    """Initialize the server components"""
    print("Initializing MuseTalk inference server...")
    
    # Initialize avatar
    avatar_manager.initialize()
    
    if not avatar_manager.is_ready():
        print("Failed to initialize avatar. Server cannot start.")
        return False
    
    print("Inference server initialization complete!")
    print("Server is now in listening state, waiting for inference requests...")
    return True

def main():
    """Main server entry point"""
    # Initialize server components
    if not initialize_server():
        sys.exit(1)
    
    # Create and configure the web application
    app = web.Application()
    app.add_routes(routes)
    
    # Setup CORS to allow cross-origin requests
    cors = cors_setup(app, defaults={
        "*": ResourceOptions(
            allow_credentials=True,
            expose_headers="*",
            allow_headers="*",
            allow_methods="*"
        )
    })
    
    # Add CORS to all routes
    for route in list(app.router.routes()):
        cors.add(route)
    
    # Start the server
    print(f"Inference server starting...")
    print(f"Server will be available at: http://{SERVER_CONFIG['host']}:{SERVER_CONFIG['port']}")
    print(f"Configured to accept connections from web clients")
    
    web.run_app(app, host=SERVER_CONFIG["host"], port=SERVER_CONFIG["port"])

if __name__ == "__main__":
    main() 