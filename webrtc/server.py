import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from aiohttp import web
import asyncio
import threading
import cv2
import numpy as np
from scripts.realtime_inference import Avatar
from musetalk.utils.blending import get_image_blending
from collections import deque
import time
import librosa
import math

routes = web.RouteTableDef()

# Global frame buffer and streaming state
frame_buffer = deque(maxlen=1000)  # Larger buffer for smooth playback
streaming_started = False
inference_complete = False
batches_processed = 0
total_batches_expected = 0
estimated_inference_time = 0
inference_start_time = None
inference_end_time = None
inference_triggered = False
avatar_fps = 25  # Default value, will be updated when avatar is created
stream_ready = False
audio_length = 0

# Pre-initialized avatar
pre_initialized_avatar = None
avatar_ready = False

def initialize_avatar():
    """Pre-initialize the avatar when server starts"""
    global pre_initialized_avatar, avatar_fps, avatar_ready, audio_length
    
    print("Pre-initializing MuseTalk avatar...")
    
    try:
        # Create and initialize the avatar
        pre_initialized_avatar = Avatar(
            avatar_id="1FrameAvatar",
            video_path="data/video/1FrameVideo.mp4",
            bbox_shift=0,
            batch_size=4,
            preparation=False,
            extra_margin=10,
            parsing_mode="jaw",
            left_cheek_width=90,
            right_cheek_width=90,
            audio_padding_length_left=2,
            audio_padding_length_right=2,
            skip_save_images=True,
            fps=25,  # Use fixed FPS value
            gpu_id=0,
            vae_type="sd-vae",
            unet_config="./models/musetalk/musetalk.json",
            unet_model_path="./models/musetalk/pytorch_model.bin",
            whisper_dir="./models/whisper",
            ffmpeg_path="./ffmpeg-4.4-amd64-static/"
        )
        
        # Update global fps value
        avatar_fps = pre_initialized_avatar.fps
        print(f"Avatar FPS set to: {avatar_fps}")
        
        # Get audio length for the timing calculation
        audio_path = "data/audio/RealTimeAudioTest.wav"
        try:
            audio_length = librosa.get_duration(filename=audio_path)
        except Exception as e:
            print(f"Could not determine audio length, defaulting to 15s. Error: {e}")
            audio_length = 15.0
        
        print(f"Audio length: {audio_length} seconds")
        print("Avatar pre-initialization complete!")
        avatar_ready = True
        
    except Exception as e:
        print(f"Error pre-initializing avatar: {e}")
        avatar_ready = False

@routes.get("/")
async def index(request):
    return web.Response(text="""
        <html>
        <head><title>Live Frame Stream</title></head>
        <body>
            <h1>Live Frame Stream (MJPEG)</h1>
            <button id="startBtn" onclick="startInference()" style="padding: 10px 20px; font-size: 16px; margin: 10px;">Start Inference</button>
            <div id="status" style="margin: 10px; font-weight: bold;"></div>
            <img id="videoStream" src="" width="1280" height="720" style="display: none;" />
            <audio id="audioPlayer" controls style="margin: 10px; display: none;">
                <source src="/audio" type="audio/wav">
                Your browser does not support the audio element.
            </audio>
            
            <script>
                let streamStarted = false;
                
                function startInference() {
                    document.getElementById('startBtn').disabled = true;
                    document.getElementById('startBtn').textContent = 'Starting...';
                    document.getElementById('status').textContent = 'Starting inference...';
                    
                    fetch('/start')
                        .then(response => response.json())
                        .then(data => {
                            if (data.success) {
                                document.getElementById('status').textContent = 'Inference started! Buffering frames...';
                                // Start showing the video stream after a short delay
                                setTimeout(() => {
                                    document.getElementById('videoStream').src = '/stream';
                                    document.getElementById('videoStream').style.display = 'block';
                                    document.getElementById('status').textContent = 'Streaming frames...';
                                    
                                    // Start checking for stream readiness
                                    checkStreamReady();
                                }, 1000); // Reduced delay since avatar is pre-initialized
                            } else {
                                document.getElementById('status').textContent = 'Error: ' + data.error;
                                document.getElementById('startBtn').disabled = false;
                                document.getElementById('startBtn').textContent = 'Start Inference';
                            }
                        })
                        .catch(error => {
                            document.getElementById('status').textContent = 'Error: ' + error;
                            document.getElementById('startBtn').disabled = false;
                            document.getElementById('startBtn').textContent = 'Start Inference';
                        });
                }
                
                function checkStreamReady() {
                    if (streamStarted) return;
                    
                    fetch('/stream_status')
                        .then(response => response.json())
                        .then(data => {
                            if (data.stream_ready && !streamStarted) {
                                streamStarted = true;
                                document.getElementById('status').textContent = 'Stream ready! Starting audio...';
                                
                                // Show and start audio player
                                const audioPlayer = document.getElementById('audioPlayer');
                                audioPlayer.style.display = 'block';
                                audioPlayer.play().then(() => {
                                    document.getElementById('status').textContent = 'Streaming with audio!';
                                }).catch(error => {
                                    console.log('Audio autoplay failed:', error);
                                    document.getElementById('status').textContent = 'Streaming with audio (click play to start audio)';
                                });
                            } else if (!data.inference_complete) {
                                // Check again in 500ms
                                setTimeout(checkStreamReady, 500);
                            }
                        })
                        .catch(error => {
                            console.log('Error checking stream status:', error);
                            // Check again in 1 second
                            setTimeout(checkStreamReady, 1000);
                        });
                }
            </script>
        </body>
        </html>
    """, content_type="text/html")

@routes.get("/start")
async def start_inference(request):
    global inference_triggered, streaming_started, avatar_fps, avatar_ready
    
    if inference_triggered:
        return web.json_response({"success": False, "error": "Inference already started"})
    
    if not avatar_ready:
        return web.json_response({"success": False, "error": "Avatar not ready. Please wait for initialization to complete."})
    
    inference_triggered = True
    streaming_started = True
    
    # Get the current event loop
    loop = asyncio.get_event_loop()
    
    # Start the inference in a background thread
    def start_inference_thread():
        global batches_processed, total_batches_expected, estimated_inference_time, inference_start_time, stream_ready
        
        print("Starting inference with pre-initialized avatar...")
        
        # Override the process_frames method to stream frames as they're processed
        def custom_process_frames(res_frame_queue, video_len, skip_save_images):
            global batches_processed, total_batches_expected, estimated_inference_time, inference_start_time, stream_ready
            inference_start_time = time.time()
            batches_processed = 0
            total_batches_expected = (video_len + pre_initialized_avatar.batch_size - 1) // pre_initialized_avatar.batch_size
            
            print(f"Starting inference with {video_len} frames, {total_batches_expected} batches expected")
            
            idx = 0
            current_batch = 0
            while idx < video_len:
                try:
                    # Get frame from the original inference queue
                    res_frame = res_frame_queue.get(block=True, timeout=1)
                    
                    # Process the frame (same logic as original process_frames)
                    bbox = pre_initialized_avatar.coord_list_cycle[idx % (len(pre_initialized_avatar.coord_list_cycle))]
                    ori_frame = pre_initialized_avatar.frame_list_cycle[idx % (len(pre_initialized_avatar.frame_list_cycle))]
                    x1, y1, x2, y2 = bbox
                    try:
                        res_frame = cv2.resize(res_frame.astype(np.uint8), (x2 - x1, y2 - y1))
                    except:
                        continue
                    mask = pre_initialized_avatar.mask_list_cycle[idx % (len(pre_initialized_avatar.mask_list_cycle))]
                    mask_crop_box = pre_initialized_avatar.mask_coords_list_cycle[idx % (len(pre_initialized_avatar.mask_coords_list_cycle))]
                    combine_frame = get_image_blending(ori_frame, res_frame, bbox, mask, mask_crop_box)
                    
                    # Add frame to buffer immediately for streaming
                    asyncio.run_coroutine_threadsafe(add_frame_to_buffer(combine_frame), loop)
                    idx += 1
                    
                    # Track batch completion
                    if idx % pre_initialized_avatar.batch_size == 0:
                        current_batch += 1
                        batches_processed = current_batch
                        
                        # Calculate estimated inference time and check if we should start streaming
                        elapsed_time = time.time() - inference_start_time
                        if elapsed_time > 0 and current_batch > 0:
                            processing_rate = batches_processed / elapsed_time
                            estimated_inference_time = total_batches_expected / processing_rate
                            estimated_time_remaining = estimated_inference_time - elapsed_time
                            
                            # Start streaming when estimated time remaining equals audio length
                            if estimated_time_remaining <= audio_length and not stream_ready:
                                stream_ready = True
                                print(f"Stream ready! Batch {current_batch}/{total_batches_expected}")
                                print(f"Estimated time remaining: {estimated_time_remaining:.1f}s, Audio length: {audio_length:.1f}s")
                        
                        # Debug: Print current batch progress
                        if current_batch % 2 == 0:  # Print every 2nd batch to avoid spam
                            if elapsed_time > 0:
                                estimated_remaining = (total_batches_expected / (batches_processed / elapsed_time)) - elapsed_time
                                print(f"Batch {current_batch}/{total_batches_expected} completed, frames in buffer: {len(frame_buffer)}, time remaining: {estimated_remaining:.1f}s")
                            else:
                                print(f"Batch {current_batch}/{total_batches_expected} completed, frames in buffer: {len(frame_buffer)}")
                    
                except __import__('queue').Empty:
                    continue
            
            # Handle remaining frames in the last batch
            if idx % pre_initialized_avatar.batch_size != 0:
                batches_processed = current_batch + 1
            
            # Signal end of inference
            asyncio.run_coroutine_threadsafe(add_frame_to_buffer(None), loop)
            global inference_complete, inference_end_time
            inference_complete = True
            inference_end_time = time.time()
            print(f"Inference completed. Total batches processed: {batches_processed}")
        
        # Replace the process_frames method temporarily
        original_process_frames = pre_initialized_avatar.process_frames
        pre_initialized_avatar.process_frames = custom_process_frames
        
        # Run the full inference pipeline
        pre_initialized_avatar.inference("data/audio/RealTimeAudioTest.wav", None, pre_initialized_avatar.fps, pre_initialized_avatar.skip_save_images)
        
        # Restore original method
        pre_initialized_avatar.process_frames = original_process_frames
    
    threading.Thread(target=start_inference_thread, daemon=True).start()
    
    return web.json_response({"success": True, "message": "Inference started"})

async def add_frame_to_buffer(frame):
    """Add a frame to the buffer for streaming"""
    frame_buffer.append(frame)

@routes.get("/audio")
async def serve_audio(request):
    """Serve the audio file for playback"""
    audio_path = "data/audio/RealTimeAudioTest.wav"
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
    global stream_ready, inference_complete
    return web.json_response({
        "stream_ready": stream_ready,
        "inference_complete": inference_complete
    })

@routes.get("/stream")
async def stream(request):
    global streaming_started, inference_complete, stream_ready, audio_length
    
    if not streaming_started:
        return web.Response(text="Inference not started", status=400)

    # Wait until stream is ready (estimated time remaining <= audio length)
    while not stream_ready and not inference_complete:
        await asyncio.sleep(0.1)
    
    print(f"beginning stream (audio length: {audio_length}s)")

    async def mjpeg_response():
        boundary = "frame"
        frame_delay = 1.0 / avatar_fps  # Use avatar's fps value
        start_time = asyncio.get_event_loop().time()
        frame_count = 0
        
        while True:
            # Wait for frames to be available in buffer
            while len(frame_buffer) == 0 and not inference_complete:
                await asyncio.sleep(0.01)
            
            # Get frame from buffer
            if len(frame_buffer) > 0:
                frame = frame_buffer.popleft()
                frame_count += 1
            else:
                # No more frames and inference is complete
                break
                
            if frame is None:
                # End of stream signal
                stream_end_time = time.time()
                if inference_end_time is not None:
                    streaming_duration = stream_end_time - inference_end_time
                    print(f"Streaming finished. Time from inference end to stream end: {streaming_duration:.2f} seconds")
                else:
                    print("Streaming finished (inference end time not available)")
                break
            
            # Calculate when this frame should be displayed
            target_time = start_time + (frame_count * frame_delay)
            current_time = asyncio.get_event_loop().time()
            
            # Wait if we're ahead of schedule
            if current_time < target_time:
                await asyncio.sleep(target_time - current_time)
            
            # Convert numpy frame to JPEG
            ret, jpeg = cv2.imencode('.jpg', frame)
            if not ret:
                continue
                
            yield (b"--" + boundary.encode() + b"\r\n"
                   b"Content-Type: image/jpeg\r\n"
                   b"Content-Length: " + str(len(jpeg)).encode() + b"\r\n\r\n" + jpeg.tobytes() + b"\r\n")
                   
    return web.Response(body=mjpeg_response(), status=200, headers={
        "Content-Type": "multipart/x-mixed-replace; boundary=frame"
    })

app = web.Application()
app.add_routes(routes)

if __name__ == "__main__":
    # Pre-initialize the avatar when server starts
    initialize_avatar()
    
    if avatar_ready:
        print("Server starting with pre-initialized avatar...")
        web.run_app(app, host="localhost", port=8080)
    else:
        print("Failed to initialize avatar. Server cannot start.")
        sys.exit(1)