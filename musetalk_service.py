import os
import sys
import time
import json
import tempfile
import threading
import queue
import base64
from pathlib import Path
from typing import Optional, Dict, Any
import requests
import cv2
import numpy as np
import torch
from flask import Flask, request, jsonify
from werkzeug.utils import secure_filename
import argparse
from omegaconf import OmegaConf
from transformers import WhisperModel

# Add the project directory to Python path
ProjectDir = os.path.abspath(os.path.dirname(__file__))
sys.path.append(ProjectDir)

from musetalk.utils.blending import get_image
from musetalk.utils.face_parsing import FaceParsing
from musetalk.utils.audio_processor import AudioProcessor
from musetalk.utils.utils import get_file_type, get_video_fps, datagen, load_all_model
from musetalk.utils.preprocessing import get_landmark_and_bbox, read_imgs, coord_placeholder

app = Flask(__name__)

# Global variables for model components
vae = None
unet = None
pe = None
whisper = None
audio_processor = None
fp = None
device = None
weight_dtype = None
timesteps = None

class MuseTalkService:
    def __init__(self, config_path: str = "configs/inference/realtime.yaml"):
        """Initialize the MuseTalk service with models and configuration"""
        # Check if config file exists
        if not os.path.exists(config_path):
            raise FileNotFoundError(f"Configuration file not found: {config_path}")
        
        self.config = OmegaConf.load(config_path)
        self.config_path = config_path  # Store config path for later use
        
        # Threading and processing control
        self.processing = False
        self.frame_count = 0
        
        # Phase control for streaming
        self.phase1_complete = False  # Phase 1: Send initial buffer
        self.phase2_active = False    # Phase 2: Send subsequent batches
        
        # Frame storage - single buffer that grows over time
        self.frame_buffer = []  # Single buffer for all processed frames
        self.buffer_lock = threading.Lock()  # Thread safety for buffer operations
        
        # Streaming control
        self.estimated_finish_time = float('inf')
        self.audio_duration = 0
        self.stream_url = None
        
        # Create inputs folder if it doesn't exist
        self.inputs_dir = "inputs"
        os.makedirs(self.inputs_dir, exist_ok=True)
        print(f"Inputs directory: {os.path.abspath(self.inputs_dir)}")
        
        # Load models
        self._load_models()
        
    def _load_models(self):
        """Load all required models using realtime.yaml configuration"""
        global vae, unet, pe, whisper, audio_processor, fp, device, weight_dtype, timesteps
        
        # Set device
        device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
        print(f"Using device: {device}")
        
        # Load realtime.yaml configuration
        inference_config = OmegaConf.load(self.config_path)
        print(f"Loaded inference config: {inference_config}")
        
        # Use default parameters from realtime_inference.py
        version = "v15"  # Default version for realtime
        unet_model_path = "./models/musetalk/pytorch_model.bin"
        unet_config = "./models/musetalk/musetalk.json"
        whisper_dir = "./models/whisper"
        vae_type = "sd-vae"
        
        # Check if model files exist
        model_paths = [
            unet_model_path,
            unet_config,
            whisper_dir
        ]
        
        for path in model_paths:
            if not os.path.exists(path):
                raise FileNotFoundError(f"Model file/directory not found: {path}")
        
        print("Loading model weights...")
        # Load model weights
        vae, unet, pe = load_all_model(
            unet_model_path=unet_model_path,
            vae_type=vae_type,
            unet_config=unet_config,
            device=device
        )
        timesteps = torch.tensor([0], device=device)
        
        # Convert to half precision for realtime inference
        pe = pe.half()
        vae.vae = vae.vae.half()
        unet.model = unet.model.half()
        
        # Move models to device
        pe = pe.to(device)
        vae.vae = vae.vae.to(device)
        unet.model = unet.model.to(device)
        
        # Initialize audio processor and Whisper
        print("Initializing audio processor and Whisper...")
        audio_processor = AudioProcessor(feature_extractor_path=whisper_dir)
        weight_dtype = unet.model.dtype
        whisper = WhisperModel.from_pretrained(whisper_dir)
        whisper = whisper.to(device=device, dtype=weight_dtype).eval()
        whisper.requires_grad_(False)
        
        # Initialize face parser for v15
        print("Initializing face parser...")
        fp = FaceParsing(
            left_cheek_width=90,
            right_cheek_width=90
        )
            
        print("All models loaded successfully")
    
    def save_audio_to_inputs(self, audio_file, original_filename: str) -> str:
        """Save uploaded audio file to inputs folder, overwriting any existing file"""
        # Get file extension
        file_ext = os.path.splitext(original_filename)[1]
        if not file_ext:
            file_ext = '.wav'  # Default to wav if no extension
        
        # Create safe filename (without timestamp to ensure single file)
        safe_filename = secure_filename(original_filename)
        base_name = os.path.splitext(safe_filename)[0]
        new_filename = f"{base_name}{file_ext}"
        
        # Clear any existing files in inputs folder
        for existing_file in os.listdir(self.inputs_dir):
            existing_path = os.path.join(self.inputs_dir, existing_file)
            if os.path.isfile(existing_path):
                os.remove(existing_path)
                print(f"Removed existing file: {existing_path}")
        
        # Save new file to inputs folder
        input_path = os.path.join(self.inputs_dir, new_filename)
        audio_file.save(input_path)
        
        print(f"Audio saved to: {input_path}")
        return input_path
    
    def process_audio_with_video(self, stream_url: str, fps: int = 25, batch_size: int = 20, 
                                bbox_shift: int = 0) -> Dict[str, Any]:
        """Process audio with video and stream frames to specified URL using realtime.yaml config.
        
        Args:
            stream_url: URL to stream the generated frames to
            fps: Frames per second for inference (default: 25)
            batch_size: Batch size for inference (default: 20)
            bbox_shift: Bounding box shift value (default: 0)
            
        Returns:
            Dict containing status and processing information
        """
        try:
            # Load realtime.yaml configuration
            inference_config = OmegaConf.load(self.config_path)
            print(f"Using inference config: {inference_config}")
            
            # Get video_path and audio_path from configuration
            video_path = inference_config.get("1FrameAvatar", {}).get("video_path")
            audio_clips = inference_config.get("1FrameAvatar", {}).get("audio_clips", {})
            
            # Get the first audio clip (assuming there's at least one)
            if not audio_clips:
                raise ValueError("No audio clips found in configuration")
            
            # Get the first audio file from the clips
            audio_path = list(audio_clips.values())[0]
            
            if not video_path or not audio_path:
                raise ValueError("video_path or audio_path not found in configuration")
            
            print(f"Using video_path from config: {video_path}")
            print(f"Using audio_path from config: {audio_path}")
            
            # Get default parameters from realtime_inference.py
            audio_padding_length_left = 2
            audio_padding_length_right = 2
            extra_margin = 10  # For v15, add extra margin
            parsing_mode = "jaw"  # Default parsing mode for v15
            
            print(f"=== Inference Configuration ===")
            print(f"FPS: {fps}")
            print(f"Batch Size: {batch_size}")
            print(f"Audio Padding: {audio_padding_length_left} left, {audio_padding_length_right} right")
            print(f"Extra Margin: {extra_margin}")
            print(f"Parsing Mode: {parsing_mode}")
            print(f"Video Path: {video_path}")
            print(f"Audio Path: {audio_path}")
            print(f"Stream URL: {stream_url}")
            print(f"BBox Shift: {bbox_shift}")
            print(f"================================")
            
            # Extract audio features
            print("Extracting audio features...")
            whisper_input_features, librosa_length = audio_processor.get_audio_feature(audio_path)
            print(f"Audio features extracted. Librosa length: {librosa_length} samples")
            
            # Calculate audio duration in seconds - librosa_length is in samples, need to divide by sampling rate
            sr = 16000  # Sampling rate from audio_processor
            audio_duration = librosa_length / sr
            print(f"Audio duration: {audio_duration:.2f} seconds ({librosa_length} samples at {sr}Hz)")
            
            # Get video FPS if it's a video file (for reference only, don't override user-specified FPS)
            if get_file_type(video_path) == "video":
                video_native_fps = get_video_fps(video_path)
                print(f"Video native FPS: {video_native_fps}")
                print(f"Using user-specified FPS: {fps}")
            
            print("Processing Whisper chunks...")
            whisper_chunks = audio_processor.get_whisper_chunk(
                whisper_input_features,
                device,
                weight_dtype,
                whisper,
                librosa_length,
                fps=fps,
                audio_padding_length_left=audio_padding_length_left,
                audio_padding_length_right=audio_padding_length_right,
            )
            print(f"Whisper chunks processed. Total chunks: {len(whisper_chunks)}")
            
            # Preprocess video frames
            print("Preprocessing video frames...")
            if get_file_type(video_path) == "video":
                # Extract frames
                temp_dir = tempfile.mkdtemp()
                save_dir_full = os.path.join(temp_dir, "frames")
                os.makedirs(save_dir_full, exist_ok=True)
                cmd = f"ffmpeg -v fatal -i {video_path} -start_number 0 {save_dir_full}/%08d.png"
                print(f"Running ffmpeg command: {cmd}")
                os.system(cmd)
                input_img_list = sorted([f for f in os.listdir(save_dir_full) if f.endswith(('.png', '.jpg', '.jpeg'))])
                input_img_list = [os.path.join(save_dir_full, f) for f in input_img_list]
                print(f"Extracted {len(input_img_list)} frames from video")
            elif get_file_type(video_path) == "image":
                input_img_list = [video_path]
                print("Using single image as input")
            else:
                raise ValueError(f"Unsupported video path type: {video_path}")
            
            # Extract landmarks and coordinates
            print("Extracting landmarks and coordinates...")
            coord_list, frame_list = get_landmark_and_bbox(input_img_list, bbox_shift)
            print(f"Landmarks extracted. Valid coordinates: {len([c for c in coord_list if c != coord_placeholder])}")
            
            # Process frames to get latents
            print("Processing frames to get latents...")
            input_latent_list = []
            for i, (bbox, frame) in enumerate(zip(coord_list, frame_list)):
                if bbox == coord_placeholder:
                    continue
                x1, y1, x2, y2 = bbox
                # For v15, add extra margin
                y2 = y2 + extra_margin
                y2 = min(y2, frame.shape[0])
                crop_frame = frame[y1:y2, x1:x2]
                crop_frame = cv2.resize(crop_frame, (256, 256), interpolation=cv2.INTER_LANCZOS4)
                latents = vae.get_latents_for_unet(crop_frame)
                input_latent_list.append(latents)
                if (i + 1) % 10 == 0:  # Log every 10 frames
                    print(f"  Processed {i + 1}/{len(coord_list)} frames for latents")
            
            print(f"Latents processing complete. Total latents: {len(input_latent_list)}")
            
            # Create cyclic lists for smooth transitions
            print("Creating cyclic lists for smooth transitions...")
            frame_list_cycle = frame_list + frame_list[::-1]
            coord_list_cycle = coord_list + coord_list[::-1]
            input_latent_list_cycle = input_latent_list + input_latent_list[::-1]
            print(f"Cyclic lists created. Cycle length: {len(frame_list_cycle)}")
            
            # Initialize streaming parameters
            self.stream_url = stream_url
            self.audio_duration = audio_duration
            self.estimated_finish_time = float('inf')
            self.phase1_complete = False
            self.phase2_active = False
            
            # Clear any existing buffer
            with self.buffer_lock:
                self.frame_buffer.clear()
            
            # Start inference thread (main thread)
            print("Starting inference thread...")
            self.processing = True
            inference_thread = threading.Thread(
                target=self._run_inference,
                args=(whisper_chunks, input_latent_list_cycle, frame_list_cycle, coord_list_cycle, 
                      batch_size, extra_margin, parsing_mode)
            )
            inference_thread.start()
            
            # Start worker thread for streaming
            print("Starting worker thread for streaming...")
            worker_thread = threading.Thread(
                target=self._worker_thread,
                args=()
            )
            worker_thread.start()
            
            # Wait for inference to complete
            print("Waiting for inference to complete...")
            inference_thread.join()
            print("Inference completed!")
            
            
            # Wait for worker thread to complete
            print("Waiting for worker thread to complete...")
            self.processing = False
            worker_thread.join()
            print("Worker thread completed!")
            
            # Cleanup
            if get_file_type(video_path) == "video":
                import shutil
                shutil.rmtree(temp_dir)
            
            return {"status": "success", "frames_processed": self.frame_count}
            
        except Exception as e:
            self.processing = False
            return {"status": "error", "message": str(e)}
    
    def _run_inference(self, whisper_chunks, input_latent_list_cycle, frame_list_cycle, coord_list_cycle, 
                      batch_size, extra_margin, parsing_mode):
        """Run inference in a separate thread using realtime.yaml configuration"""
        try:
            # Perform inference
            video_num = len(whisper_chunks)
            print(f"=== Starting Inference ===")
            print(f"Total whisper chunks: {video_num}")
            print(f"Batch size: {batch_size}")
            print(f"Expected total frames: {video_num}")
            print(f"Audio duration: {self.audio_duration:.2f}s")
            print(f"==========================")
            
            gen = datagen(
                whisper_chunks=whisper_chunks,
                vae_encode_latents=input_latent_list_cycle,
                batch_size=batch_size,
                delay_frame=0,
                device=device,
            )
            
            frame_idx = 0
            batch_count = 0
            start_time = time.time()
            frameTime = time.time()  # For estimated time calculation
            
            for i, (whisper_batch, latent_batch) in enumerate(gen):
                batch_count += 1
                batch_start_time = time.time()
                
                print(f"Processing batch {batch_count}/{video_num//batch_size + (1 if video_num % batch_size else 0)}")
                print(f"  Batch size: {whisper_batch.shape[0] if hasattr(whisper_batch, 'shape') else 'N/A'}")
                print(f"  Current frame index: {frame_idx}")
                
                # Process audio features
                audio_feature_batch = pe(whisper_batch)
                latent_batch = latent_batch.to(dtype=unet.model.dtype)
                
                # Run UNet inference
                pred_latents = unet.model(latent_batch, timesteps, encoder_hidden_states=audio_feature_batch).sample
                recon = vae.decode_latents(pred_latents)
                
                # Process frames in this batch
                frames_in_batch = 0
                
                for res_frame in recon:
                    # Process frame for streaming
                    bbox = coord_list_cycle[frame_idx % len(coord_list_cycle)]
                    ori_frame = frame_list_cycle[frame_idx % len(frame_list_cycle)]
                    x1, y1, x2, y2 = bbox
                    
                    # For v15, add extra margin
                    y2 = y2 + extra_margin
                    y2 = min(y2, ori_frame.shape[0])
                    
                    try:
                        res_frame = cv2.resize(res_frame.astype(np.uint8), (x2-x1, y2-y1))
                    except:
                        frame_idx += 1
                        continue
                    
                    # Blend frame using parsing mode from config
                    combine_frame = get_image(ori_frame, res_frame, [x1, y1, x2, y2], 
                                            mode=parsing_mode, fp=fp)
                    
                    # Encode frame as JPEG
                    _, buffer = cv2.imencode('.jpg', combine_frame)
                    frame_data = buffer.tobytes()
                    
                    # Push frame to main buffer immediately for lower latency streaming
                    with self.buffer_lock:
                        self.frame_buffer.append({
                            'frame_number': frame_idx,
                            'frame_data': frame_data
                        })
                    
                    frame_idx += 1
                    frames_in_batch += 1
                
                
                batch_time = time.time() - batch_start_time
                elapsed_time = time.time() - start_time
                avg_fps = frame_idx / elapsed_time if elapsed_time > 0 else 0
                
                # Calculate estimated time to finish and update for worker thread
                if batch_count >= 1:
                    self.estimated_finish_time = (time.time() - frameTime) * (video_num - frame_idx) / frame_idx
                    print(f"  Estimated time to finish: {self.estimated_finish_time:.2f}s")
                    print(f"  Audio duration: {self.audio_duration:.2f}s")
                
                print(f"  Batch completed in {batch_time:.2f}s")
                print(f"  Frames in this batch: {frames_in_batch}")
                print(f"  Total frames processed: {frame_idx}/{video_num}")
                print(f"  Buffer size: {len(self.frame_buffer)}")
                print(f"  Average FPS: {avg_fps:.2f}")
                print(f"  Progress: {(frame_idx/video_num)*100:.1f}%")
                print("  ---")
            
            # Store frame count for return value
            self.frame_count = frame_idx
            total_time = time.time() - start_time
            final_fps = frame_idx / total_time if total_time > 0 else 0
            
            print(f"=== Inference Complete ===")
            print(f"Total frames generated: {frame_idx}")
            print(f"Total time: {total_time:.2f}s")
            print(f"Final FPS: {final_fps:.2f}")
            print(f"==========================")
            
        except Exception as e:
            print(f"Error in inference thread: {e}")
            self.processing = False
    
    def _worker_thread(self):
        """Worker thread that handles 2-phase streaming logic"""
        total_frames_sent = 0
        
        print(f"=== Starting Worker Thread ===")
        print(f"Stream URL: {self.stream_url}")
        print(f"Audio duration: {self.audio_duration:.2f}s")
        print(f"Waiting for estimated time to be <= audio duration...")
        print(f"===============================")
        
        # Phase 0: Wait for estimated time to be <= audio duration
        wait_count = 0
        while self.estimated_finish_time > self.audio_duration and self.processing:
            time.sleep(0.1)  # Check every 100ms
            wait_count += 1
            if wait_count % 50 == 0:  # Log every 5 seconds
                print(f"  Still waiting... (waited {wait_count*0.1:.1f}s)")
                print(f"  Estimated finish time: {self.estimated_finish_time:.2f}s")
                print(f"  Audio duration: {self.audio_duration:.2f}s")
                print(f"  Buffer size: {len(self.frame_buffer)}")
        
        # Check if we exited because processing stopped
        if not self.processing:
            print(f"*** PROCESSING STOPPED BEFORE PHASE 1 ***")
            return
        
        print(f"*** PHASE 1: SENDING INITIAL BUFFER ***")
        print(f"  Estimated finish time ({self.estimated_finish_time:.2f}s) <= Audio duration ({self.audio_duration:.2f}s)")
        
        # Phase 1: Send entire buffer to web page
        with self.buffer_lock:
            initial_buffer = self.frame_buffer.copy()
        
        if initial_buffer:
            try:
                print(f"  SENDING INITIAL BUFFER with {len(initial_buffer)} frames...")
                buffer_data = {
                    'frames': [
                        {
                            'frame_number': frame['frame_number'],
                            'frame_data': base64.b64encode(frame['frame_data']).decode('utf-8')
                        }
                        for frame in initial_buffer
                    ],
                    'total_frames': len(initial_buffer),
                    'timestamp': time.time()
                }
                
                response = requests.post(
                    self.stream_url,
                    json=buffer_data,
                    headers={'Content-Type': 'application/json'},
                    timeout=10
                )
                
                if response.status_code == 200:
                    frames_sent = len(initial_buffer)
                    total_frames_sent += frames_sent
                    print(f"  SUCCESS: Sent initial buffer with {frames_sent} frames")
                    print(f"  Total frames sent so far: {total_frames_sent}")
                    
                    # Clear the buffer after successful send to prevent duplicates
                    with self.buffer_lock:
                        self.frame_buffer.clear()
                        print(f"  BUFFER CLEARED - size now: 0")
                    
                    self.phase1_complete = True
                else:
                    print(f"  ERROR: Failed to send initial buffer, status: {response.status_code}")
                    return
                    
            except Exception as e:
                print(f"  ERROR sending initial buffer: {e}")
                return
        else:
            print(f"  No frames in initial buffer")
            return
        
        print(f"*** PHASE 2: SENDING SUBSEQUENT BATCHES ***")
        self.phase2_active = True
        
        # Phase 2: Send each batch as it arrives in the buffer
        # Continue until processing stops AND buffer is empty
        while self.processing or len(self.frame_buffer) > 0:
            # Check for new frames in buffer
            with self.buffer_lock:
                current_buffer_size = len(self.frame_buffer)
            
            if current_buffer_size > 0:
                # New batch available - send it immediately
                print(f"  Found {current_buffer_size} new frames in buffer")
                
                # Get all frames in buffer (this is the new batch)
                with self.buffer_lock:
                    new_batch = self.frame_buffer.copy()
                    self.frame_buffer.clear()  # Clear buffer after sending
                
                try:
                    print(f"  SENDING BATCH with {len(new_batch)} frames...")
                    buffer_data = {
                        'frames': [
                            {
                                'frame_number': frame['frame_number'],
                                'frame_data': base64.b64encode(frame['frame_data']).decode('utf-8')
                            }
                            for frame in new_batch
                        ],
                        'total_frames': len(new_batch),
                        'timestamp': time.time()
                    }
                    
                    response = requests.post(
                        self.stream_url,
                        json=buffer_data,
                        headers={'Content-Type': 'application/json'},
                        timeout=10
                    )
                    
                    if response.status_code == 200:
                        frames_sent = len(new_batch)
                        total_frames_sent += frames_sent
                        print(f"  SUCCESS: Sent batch with {frames_sent} frames")
                        print(f"  Total frames sent so far: {total_frames_sent}")
                    else:
                        print(f"  ERROR: Failed to send batch, status: {response.status_code}")
                        
                except Exception as e:
                    print(f"  ERROR sending batch: {e}")
            
            # Small sleep to prevent busy waiting, but keep latency low
            time.sleep(0.02)
            
            # Log status if processing stopped but buffer not empty
            if not self.processing and current_buffer_size > 0:
                print(f"  Processing stopped, but {current_buffer_size} frames still in buffer")
        
        # All frames have been sent
        print(f"  All frames sent - buffer is empty and processing stopped")
        
        # Send finished signal
        try:
            print(f"  SENDING FINISHED SIGNAL...")
            finished_data = {
                'status': 'finished',
                'total_frames_sent': total_frames_sent,
                'timestamp': time.time(),
                'message': 'Streaming completed successfully'
            }
            
            response = requests.post(
                self.stream_url,
                json=finished_data,
                headers={'Content-Type': 'application/json'},
                timeout=10
            )
            
            if response.status_code == 200:
                print(f"  SUCCESS: Sent finished signal")
            else:
                print(f"  ERROR: Failed to send finished signal, status: {response.status_code}")
                
        except Exception as e:
            print(f"  ERROR sending finished signal: {e}")
        
        print(f"=== Worker Thread Complete ===")
        print(f"Total frames sent: {total_frames_sent}")
        print(f"=============================")

# Global service instance
service = None

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({"status": "healthy", "models_loaded": service is not None})

@app.route('/process', methods=['POST'])
def process_audio():
    """Process audio file with video and stream frames"""
    global service
    
    if service is None:
        return jsonify({"error": "Service not initialized"}), 500
    
    try:
        # Check if audio file is provided
        if 'audio' not in request.files:
            return jsonify({"error": "No audio file provided"}), 400
        
        audio_file = request.files['audio']
        if audio_file.filename == '':
            return jsonify({"error": "No audio file selected"}), 400
        
        # Get parameters
        stream_url = request.form.get('stream_url')
        fps = int(request.form.get('fps', 25))
        batch_size = int(request.form.get('batch_size', 20))
        bbox_shift = int(request.form.get('bbox_shift', 0))
        
        if not stream_url:
            return jsonify({"error": "stream_url is required"}), 400
        
        # Save audio file to inputs folder
        saved_audio_path = service.save_audio_to_inputs(audio_file, audio_file.filename)
        
        try:
            # Start processing in background thread
            processing_thread = threading.Thread(
                target=service.process_audio_with_video,
                args=(stream_url, fps, batch_size, bbox_shift)
            )
            processing_thread.start()
            
            # Return immediately - processing continues in background
            return jsonify({
                "status": "processing_started",
                "message": "Audio processing started in background"
            })
            
        except Exception as e:
            return jsonify({"error": str(e)}), 500
            
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/status', methods=['GET'])
def get_status():
    """Get current processing status"""
    global service
    if service is None:
        return jsonify({"status": "not_initialized"})
    
    return jsonify({
        "status": "processing" if service.processing else "idle",
        "buffer_size": len(service.frame_buffer),
        "phase1_complete": service.phase1_complete,
        "phase2_active": service.phase2_active,
        "estimated_finish_time": service.estimated_finish_time,
        "audio_duration": service.audio_duration
    })

def main():
    parser = argparse.ArgumentParser(description='MuseTalk Service')
    parser.add_argument('--config', type=str, default='configs/inference/realtime.yaml',
                       help='Path to configuration file')
    parser.add_argument('--host', type=str, default='0.0.0.0',
                       help='Host to bind the server to')
    parser.add_argument('--port', type=int, default=8085,
                       help='Port to bind the server to')
    parser.add_argument('--debug', action='store_true',
                       help='Enable debug mode')
    
    args = parser.parse_args()
    
    # Initialize service
    global service
    print("Initializing MuseTalk Service...")
    try:
        service = MuseTalkService(args.config)
        print("Service initialized successfully")
    except Exception as e:
        print(f"Failed to initialize service: {e}")
        print("Please check:")
        print("1. Configuration file exists and is valid")
        print("2. Model files are downloaded and paths are correct")
        print("3. All dependencies are installed")
        return
    
    # Start Flask app
    app.run(host=args.host, port=args.port, debug=args.debug)

if __name__ == '__main__':
    main()
