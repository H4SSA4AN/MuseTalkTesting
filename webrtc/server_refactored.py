"""
Refactored MuseTalk streaming server
"""

import sys
import os
import asyncio
import threading
import time
import argparse
import requests
import cv2
import base64
import numpy as np
from aiohttp import web, ClientConnectionResetError
import librosa
import queue

# Add parent directory to path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Import our modular components
try:
    from .config import STREAMING_CONFIG, SERVER_CONFIG
    from .state_manager import StreamingState
    from .avatar_manager import AvatarManager
    from .streaming_handler import StreamingHandler
    from .answers_watcher import AnswersWatcher
except ImportError:
    # Fallback for direct script execution
    from config import STREAMING_CONFIG, SERVER_CONFIG
    from state_manager import StreamingState
    from avatar_manager import AvatarManager
    from streaming_handler import StreamingHandler
    from answers_watcher import AnswersWatcher

# Initialize global components
state = StreamingState(frame_buffer_size=STREAMING_CONFIG["frame_buffer_size"])
avatar_manager = AvatarManager()
streaming_handler = None
answers_watcher: AnswersWatcher | None = None
current_audio_path = None  # Store the current audio file path
mini_omni_url = None  # Store the Mini-Omni server URL

routes = web.RouteTableDef()


@routes.get("/")
async def index(request):
    """Serve the main HTML page"""
    try:
        # Try relative path first
        with open("templates/index.html", "r") as f:
            html_content = f.read()
        return web.Response(text=html_content, content_type="text/html")
    except FileNotFoundError:
        try:
            # Try absolute path
            with open("webrtc/templates/index.html", "r") as f:
                html_content = f.read()
            return web.Response(text=html_content, content_type="text/html")
        except FileNotFoundError:
            return web.Response(text="Template file not found", status=404)


@routes.post("/start")
async def start_inference(request):
    """Start the inference process, accepting custom FPS and batch size."""
    global state, avatar_manager, streaming_handler
    
    if state.inference_triggered:
        return web.json_response({"success": False, "error": "Inference already started"}, headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "POST, OPTIONS",
            "Access-Control-Allow-Headers": "*"
        })
    
    if not avatar_manager.is_ready():
        return web.json_response({"success": False, "error": "Avatar not ready. Please wait for initialization to complete."}, headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "POST, OPTIONS",
            "Access-Control-Allow-Headers": "*"
        })

    try:
        data = await request.json()
        fps = data.get('fps', avatar_manager.get_fps())
        batch_size = data.get('batch_size', avatar_manager.get_batch_size())
        print(f"[Inference] Received custom settings - FPS: {fps}, Batch Size: {batch_size}")
    except Exception:
        # Fallback to defaults if JSON body is missing or malformed
        fps = avatar_manager.get_fps()
        batch_size = avatar_manager.get_batch_size()
        print(f"[Inference] No custom settings received, using defaults - FPS: {fps}, Batch Size: {batch_size}")

    # Reset state for new inference
    state.reset_inference_state()
    
    # Calculate and set audio length for the current inference
    audio_path = current_audio_path if current_audio_path else avatar_manager.get_audio_path()
    try:
        state.audio_length = librosa.get_duration(path=audio_path) # Use path instead of filename
        print(f"[Inference] Calculated audio duration for '{os.path.basename(audio_path)}': {state.audio_length:.2f}s")
    except Exception as e:
        print(f"[Inference] Could not get audio duration, using default. Error: {e}")
        state.audio_length = 0.0 # Fallback

    state.start_inference()
    
    # Initialize streaming handler with potentially new FPS
    avatar_manager.set_fps(fps)
    avatar_manager.set_batch_size(batch_size)
    streaming_handler = StreamingHandler(state, avatar_manager)
    
    # Get the current event loop
    loop = asyncio.get_event_loop()
    
    # Create a queue for communication between the inference and processing threads
    frame_queue = queue.Queue(maxsize=10) # Buffer a few batches

    # --- Thread 1: GPU Inference (Producer) ---
    def start_inference_thread():
        print(f"[GPU Thread] Starting inference (FPS: {fps}, Batch Size: {batch_size})")
        try:
            avatar = avatar_manager.get_avatar()
            avatar.inference(
                audio_path,
                None,
                fps,
                avatar_manager.get_skip_save_images(),
                batch_size,
                frame_queue
            )
            print("[GPU Thread] Inference completed.")
        except Exception as e:
            print(f"[GPU Thread] Error during inference: {e}")
            import traceback
            traceback.print_exc()
            frame_queue.put(None) # Ensure processor thread terminates on error
    
    # --- Thread 2: CPU Processing (Consumer) ---
    def start_processing_thread():
        print("[CPU Thread] Starting frame processor.")
        try:
            # Calculate total batches once at the beginning
            total_frames = int(state.audio_length * avatar_manager.get_fps())
            batch_size = avatar_manager.get_batch_size()
            state.total_batches_expected = (total_frames + batch_size - 1) // batch_size if batch_size > 0 else 0
            print("=" * 60)
            print(f"[CPU Thread] Total batches expected: {state.total_batches_expected}")
            print("=" * 60)

            while True:
                frames_batch = frame_queue.get()
                if frames_batch is None:
                    # End of stream signal
                    print("[CPU Thread] End of stream signal received.")
                    break
                
                # This is the CPU-intensive part
                processed_frames = streaming_handler._process_frame_batch(frames_batch)
                
                # Efficiently hand off to the async world
                asyncio.run_coroutine_threadsafe(
                    streaming_handler._add_frames_to_buffer_async(processed_frames), 
                    loop
                )

                # Increment batch counter and print progress
                state.batches_processed += 1
                streaming_handler._print_batch_progress(
                    state.batches_processed, state.total_batches_expected, state.inference_start_time
                )

                # Check if we should start streaming based on the new conditions
                if not state.stream_ready and state.batches_processed >= 3:
                    elapsed_time = time.time() - state.inference_start_time
                    if state.batches_processed > 0:
                        avg_time_per_batch = elapsed_time / state.batches_processed
                        remaining_batches = state.total_batches_expected - state.batches_processed
                        eta = remaining_batches * avg_time_per_batch
                        
                        if eta <= state.audio_length:
                            print(f"[Stream Ready] Condition met. ETA ({eta:.2f}s) <= Audio Length ({state.audio_length:.2f}s). Batches processed: {state.batches_processed}.")
                            loop.call_soon_threadsafe(state.set_stream_ready)
            
            # Final completion signal
            loop.call_soon_threadsafe(state.complete_inference)
            print("[CPU Thread] Processing finished.")

        except Exception as e:
            print(f"[CPU Thread] Error during processing: {e}")
            import traceback
            traceback.print_exc()

    # Start both threads
    threading.Thread(target=start_inference_thread, daemon=True).start()
    threading.Thread(target=start_processing_thread, daemon=True).start()
    
    return web.json_response({
        "success": True, 
        "message": "Inference started",
        "fps": fps
    }, headers={
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "POST, OPTIONS",
        "Access-Control-Allow-Headers": "*"
    })


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


@routes.get("/health")
async def health(request):
    """Health check endpoint"""
    return web.json_response({
        "status": "ok",
        "server": "MuseTalk WebRTC",
        "avatar_ready": avatar_manager.is_ready(),
        "streaming_ready": state.stream_ready if state else False
    }, headers={
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET, OPTIONS",
        "Access-Control-Allow-Headers": "*"
    })


@routes.get("/stream_status")
async def stream_status(request):
    """Check if streaming is ready to start"""
    global avatar_manager
    return web.json_response({
        "stream_ready": state.stream_ready,
        "inference_complete": state.inference_complete,
        "streaming_started": state.streaming_started,
        "inference_triggered": state.inference_triggered,
        "fps": avatar_manager.get_fps(),
        "inference_end_time": state.inference_end_time
    }, headers={
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET, OPTIONS",
        "Access-Control-Allow-Headers": "*"
    })


@routes.post("/upload_answer")
async def upload_answer(request: web.Request) -> web.Response:
    """Upload answer WAV file from Mini-Omni"""
    global current_audio_path
    
    try:
        reader = await request.multipart()
        field = await reader.next()
        
        if field is None or field.name != "file":
            # Support raw body as wav
            raw = await request.read()
            if not raw:
                return web.json_response({"ok": False, "error": "no file"}, status=400, headers={
                    "Access-Control-Allow-Origin": "*",
                    "Access-Control-Allow-Methods": "POST, OPTIONS",
                    "Access-Control-Allow-Headers": "*"
                })
            filename = f"Answer_{int(time.time()*1000)}.wav"
        else:
            filename = field.filename or f"Answer_{int(time.time()*1000)}.wav"
        
        # Save to answers directory
        answers_dir = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "answers"))
        save_path = os.path.join(answers_dir, filename)
        
        with open(save_path, "wb") as f:
            if field is None:
                # Raw body
                f.write(raw)
            else:
                # Multipart file
                while True:
                    chunk = await field.read_chunk()
                    if not chunk:
                        break
                    f.write(chunk)
        
        # Update current audio path
        current_audio_path = save_path
        print(f"[MuseTalk] Uploaded answer received: {save_path}")
        
        return web.json_response({"ok": True, "path": os.path.basename(save_path)}, headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "POST, OPTIONS",
            "Access-Control-Allow-Headers": "*"
        })
        
    except Exception as e:
        print(f"[MuseTalk] Upload error: {e}")
        return web.json_response({"ok": False, "error": str(e)}, status=500, headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "POST, OPTIONS",
            "Access-Control-Allow-Headers": "*"
        })


@routes.options("/stream")
async def stream_options(request):
    """Handle CORS preflight for stream endpoint"""
    return web.Response(
        status=200,
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, OPTIONS",
            "Access-Control-Allow-Headers": "*"
        }
    )


@routes.options("/start")
async def start_options(request):
    """Handle CORS preflight for start endpoint"""
    return web.Response(
        status=200,
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, OPTIONS",
            "Access-Control-Allow-Headers": "*"
        }
    )


@routes.options("/upload_answer")
async def upload_answer_options(request):
    """Handle CORS preflight for upload_answer endpoint"""
    return web.Response(
        status=200,
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "POST, OPTIONS",
            "Access-Control-Allow-Headers": "*"
        }
    )


@routes.options("/stream_status")
async def stream_status_options(request):
    """Handle CORS preflight for stream_status endpoint"""
    return web.Response(
        status=200,
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, OPTIONS",
            "Access-Control-Allow-Headers": "*"
        }
    )


@routes.options("/health")
async def health_options(request):
    """Handle CORS preflight for health endpoint"""
    return web.Response(
        status=200,
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, OPTIONS",
            "Access-Control-Allow-Headers": "*"
        }
    )


@routes.options("/stream")
async def stream_options(request):
    """Handle CORS preflight for stream endpoint"""
    return web.Response(
        status=200,
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, OPTIONS",
            "Access-Control-Allow-Headers": "*"
        }
    )


@routes.options("/stream_ready")
async def stream_ready_options(request):
    """Handle CORS preflight for stream_ready endpoint"""
    return web.Response(
        status=200,
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, OPTIONS",
            "Access-Control-Allow-Headers": "*"
        }
    )


@routes.post("/reset")
async def reset_state(request):
    """Explicitly reset the server's inference state."""
    global state
    print("[State] Received request to reset state.")
    if state:
        state.reset_inference_state()
    return web.json_response({"success": True, "message": "Server state reset."})


async def notify_mini_omni_stream_ready():
    """Notify Mini-Omni server that streaming is ready"""
    global mini_omni_url
    if not mini_omni_url:
        return
    
    try:
        # Send a notification to Mini-Omni that streaming is ready
        notification_url = f"{mini_omni_url.rstrip('/')}/musetalk_stream_ready"
        response = requests.post(notification_url, json={
            "status": "ready",
            "stream_url": f"http://{SERVER_CONFIG['host']}:{SERVER_CONFIG['port']}/stream"
        }, timeout=5)
        print(f"[MuseTalk] Notified Mini-Omni server: {response.status_code}")
    except Exception as e:
        print(f"[MuseTalk] Failed to notify Mini-Omni server: {e}")


@routes.get("/stream")
async def stream(request):
    """Handle MJPEG streaming with improved error handling"""
    global state, streaming_handler
    
    print(f"[Stream] Stream request received. State: streaming_started={state.streaming_started}, stream_ready={state.stream_ready}, inference_complete={state.inference_complete}")
    
    if not state.streaming_started:
        return web.Response(text="Inference not started", status=400, headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, OPTIONS",
            "Access-Control-Allow-Headers": "*"
        })

    # Wait until stream is ready with timeout
    wait_count = 0
    max_wait_time = 60  # 60 seconds timeout
    while not state.stream_ready and not state.inference_complete:
        await asyncio.sleep(0.1)
        wait_count += 1
        if wait_count % 50 == 0:  # Print every 5 seconds
            print(f"[Stream] Still waiting... stream_ready={state.stream_ready}, inference_complete={state.inference_complete}, buffer_size={state.get_buffer_size()}")
        
        # Timeout after max_wait_time seconds
        if wait_count >= max_wait_time * 10:  # 0.1s intervals
            print(f"[Stream] Timeout waiting for stream to be ready after {max_wait_time} seconds")
            return web.Response(text="Stream timeout", status=408, headers={
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "GET, OPTIONS",
                "Access-Control-Allow-Headers": "*"
            })
    
    print(f"[Stream] Beginning stream (audio length: {state.audio_length:.2f}s, buffer_size={state.get_buffer_size()})")
    
    # Notify Mini-Omni server that streaming is ready
    await notify_mini_omni_stream_ready()

    # Create a streaming response with proper CORS headers
    response = web.StreamResponse(
        status=200,
        headers={
            "Content-Type": "multipart/x-mixed-replace; boundary=frame",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, OPTIONS",
            "Access-Control-Allow-Headers": "*",
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"  # Disable proxy buffering
        }
    )
    
    try:
        await response.prepare(request)
    except Exception as e:
        print(f"[Stream] Error preparing response: {e}")
        return web.Response(text="Stream preparation failed", status=500, headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, OPTIONS",
            "Access-Control-Allow-Headers": "*"
        })
    
    # Stream the MJPEG data with robust error handling
    try:
        # Start with a heartbeat to keep the connection alive
        heartbeat_task = asyncio.create_task(send_heartbeat(response))
        
        # Wait for the first frame to be ready
        try:
            await asyncio.wait_for(state.first_frame_event.wait(), timeout=max_wait_time)
        except asyncio.TimeoutError:
            print(f"[Stream] Timeout waiting for the first frame after {max_wait_time} seconds.")
            return response
        finally:
            # Stop the heartbeat once the first frame is ready
            heartbeat_task.cancel()

        # Stream actual frames
        async for chunk in streaming_handler.mjpeg_response():
            try:
                if not response.prepared:
                    print("[Stream] Client disconnected before stream could start.")
                    break
                await response.write(chunk)
            except (ConnectionResetError, ClientConnectionResetError) as e:
                print(f"[Stream] Client disconnected: {e.__class__.__name__}. Stopping stream.")
                break
            except Exception as e:
                print(f"[Stream] Unexpected error writing chunk: {e}. Stopping stream.")
                break
        
        # Try to send EOF, but ignore errors if connection is already closed
        try:
            await response.write_eof()
        except (ConnectionResetError, ClientConnectionResetError):
            print("[Stream] Could not send EOF, connection already closed.")
            
    except Exception as e:
        print(f"[Stream] Unhandled exception in streaming loop: {e}")
    finally:
        print("[Stream] Stream handler finished.")
    
    return response


async def send_heartbeat(response):
    """Sends an empty MJPEG boundary every second to keep the connection alive."""
    boundary = b"--frame\r\n\r\n"
    while True:
        try:
            if not response.prepared:
                break
            await response.write(boundary)
            await asyncio.sleep(1)
        except (ConnectionResetError, ClientConnectionResetError):
            # Client disconnected, stop the heartbeat
            break
        except Exception as e:
            # Another error occurred, stop the heartbeat
            print(f"[Heartbeat] Error: {e}")
            break
    print("[Heartbeat] Stopped.")


@routes.get("/stream_ready")
async def check_stream_ready(request):
    """Check if stream is ready to start"""
    global state
    
    return web.json_response({
        "stream_ready": state.stream_ready,
        "inference_complete": state.inference_complete,
        "streaming_started": state.streaming_started,
        "inference_triggered": state.inference_triggered,
        "buffer_size": state.get_buffer_size()
    }, headers={
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET, OPTIONS",
        "Access-Control-Allow-Headers": "*"
    })


@routes.get("/test_frames")
async def test_frames(request):
    """Test endpoint to manually add some test frames to the buffer"""
    global state
    
    # Add some test frames to the buffer
    test_frame = np.zeros((480, 640, 3), dtype=np.uint8)
    test_frame[:, :, 0] = 255  # Blue channel
    
    # Add text to the frame
    cv2.putText(test_frame, "TEST FRAME", (50, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
    
    # Add 5 test frames
    for i in range(5):
        frame_copy = test_frame.copy()
        cv2.putText(frame_copy, f"Frame {i+1}", (50, 100), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
        state.add_frame_to_buffer(frame_copy)
        print(f"[Test] Added test frame {i+1}")
    
    return web.json_response({
        "status": "success",
        "message": "Added 5 test frames to buffer",
        "buffer_size": state.get_buffer_size()
    }, headers={
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET, OPTIONS",
        "Access-Control-Allow-Headers": "*"
    })


def initialize_server():
    """Initialize the server components"""
    print("Initializing MuseTalk streaming server...")
    
    # Clear answers folder on startup
    answers_dir = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "answers"))
    if os.path.exists(answers_dir):
        for file in os.listdir(answers_dir):
            if file.lower().endswith('.wav'):
                file_path = os.path.join(answers_dir, file)
                try:
                    os.remove(file_path)
                    print(f"Cleared old answer file: {file_path}")
                except Exception as e:
                    print(f"Could not remove {file_path}: {e}")
    else:
        os.makedirs(answers_dir, exist_ok=True)
        print(f"Created answers directory: {answers_dir}")
    
    # Initialize avatar
    avatar_manager.initialize()
    
    if not avatar_manager.is_ready():
        print("Failed to initialize avatar. Server cannot start.")
        return False
    
    # The watcher is now disabled, as inference is triggered explicitly by Mini-Omni server
    # # Set up answers watcher to trigger inference automatically when new audio arrives
    # def on_new_answer(path: str):
    #     # If inference hasn't been triggered, kick it off via HTTP start
    #     def trigger():
    #         try:
    #             print(f"[MuseTalk][Watcher] Triggering inference due to new answer: {path}")
    #             # Update the current audio path
    #             global current_audio_path
    #             current_audio_path = path
    #             print(f"[MuseTalk][Watcher] Updated audio path to: {path}")
                
    #             # Create a mock request object for the start_inference function
    #             class MockRequest:
    #                 def __init__(self):
    #                     pass
                
    #             # Use asyncio.run_coroutine_threadsafe to run the async function from the thread
    #             loop = asyncio.get_event_loop()
    #             if loop.is_running():
    #                 future = asyncio.run_coroutine_threadsafe(start_inference(MockRequest()), loop)
    #                 future.result()  # Wait for completion
    #             else:
    #                 # If no event loop is running, create a new one
    #                 asyncio.run(start_inference(MockRequest()))
                    
    #         except Exception as e:
    #             print(f"[MuseTalk][Watcher] Trigger error: {e}")
    #     trigger()

    # global answers_watcher
    # answers_dir = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "answers"))
    # answers_watcher = AnswersWatcher(answers_dir, on_new_answer)
    # answers_watcher.start()

    print("Server initialization complete!")
    return True


async def cors_middleware(app, handler):
    """CORS middleware to handle all requests"""
    async def middleware(request):
        # Handle preflight requests
        if request.method == 'OPTIONS':
            return web.Response(
                status=200,
                headers={
                    "Access-Control-Allow-Origin": "*",
                    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
                    "Access-Control-Allow-Headers": "*",
                    "Access-Control-Max-Age": "86400"
                }
            )
        
        # Handle actual requests
        response = await handler(request)
        
        # Add CORS headers to all responses
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "*"
        
        return response
    
    return middleware


def main():
    """Main server entry point"""
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='MuseTalk WebRTC Streaming Server')
    parser.add_argument('--mini-omni-url', type=str, help='URL of the Mini-Omni server (e.g., http://localhost:5000)')
    parser.add_argument('--host', type=str, default=SERVER_CONFIG["host"], help='Host to bind to')
    parser.add_argument('--port', type=int, default=SERVER_CONFIG["port"], help='Port to bind to')
    
    args = parser.parse_args()
    
    # Set global variables
    global mini_omni_url
    mini_omni_url = args.mini_omni_url
    
    # Update server config
    SERVER_CONFIG["host"] = args.host
    SERVER_CONFIG["port"] = args.port
    
    # Initialize server components
    if not initialize_server():
        sys.exit(1)
    
    # Create and configure the web application
    app = web.Application()
    app.middlewares.append(cors_middleware)
    app.add_routes(routes)
    
    # Start the server
    print(f"Server starting with pre-initialized avatar...")
    print(f"Server will be available at: http://{SERVER_CONFIG['host']}:{SERVER_CONFIG['port']}")
    if mini_omni_url:
        print(f"Mini-Omni server URL: {mini_omni_url}")
    web.run_app(app, host=SERVER_CONFIG["host"], port=SERVER_CONFIG["port"])


if __name__ == "__main__":
    main() 