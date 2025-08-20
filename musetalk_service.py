import os
import sys
import time
import json
import tempfile
import threading
import base64
from pathlib import Path
from typing import Optional, Dict, Any
import requests
import cv2
import numpy as np
import torch
from flask import Flask, request, jsonify, Response
from werkzeug.utils import secure_filename
import argparse
from omegaconf import OmegaConf
from transformers import WhisperModel
import asyncio
import fractions
from aiortc import RTCPeerConnection, RTCSessionDescription, MediaStreamTrack
from av import VideoFrame
import math
import queue

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
        self.inference_complete = False  # New flag to track when inference thread is done

        # Phase control for streaming (kept for status visibility)
        self.phase1_complete = False
        self.phase2_active = False

        # Frame storage - single buffer that grows over time
        self.frame_buffer = []  # Single buffer for all processed frames
        self.buffer_lock = threading.Lock()  # Thread safety for buffer operations
        
        # Buffer queue for sending frames without blocking inference
        self.buffer_queue = queue.Queue()
        self.buffer_sender_thread = None
        self.buffer_sender_stop = False
        
        # Streaming control
        self.estimated_finish_time = float('inf')
        self.audio_duration = 0
        self.stream_url = None
        self.total_frames_expected = 0  # Track total frames that should be generated
        self._worker_frames_sent = 0  # Kept for logging compatibility
        self.fps = 25

        # WebRTC components
        self.webrtc_pc = None
        self.webrtc_track = None
        self.webrtc_read_index = 0
        self._start_signal_sent = False
        self._finished_signal_sent = False
        self._streaming_started = False
        self._aio_loop = asyncio.new_event_loop()
        self._aio_thread = threading.Thread(target=self._run_aio_loop, daemon=True)
        self._aio_thread.start()
        self._worker_thread = None
        self._worker_stop = False
        self._worker_frames_sent = 0
        
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
    
    def _run_aio_loop(self):
        asyncio.set_event_loop(self._aio_loop)
        try:
            self._aio_loop.run_forever()
        finally:
            self._aio_loop.close()

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
            batch_size: Batch size for inference (default: 20, or user-specified from web page)
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
            self.fps = fps
            self.webrtc_read_index = 0
            self._start_signal_sent = False
            self._finished_signal_sent = False
            
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
            
            # Start buffer sender thread (dedicated thread for sending frames)
            print("Starting buffer sender thread...")
            self.buffer_sender_stop = False
            self.buffer_sender_thread = threading.Thread(
                target=self._buffer_sender_thread,
                args=()
            )
            self.buffer_sender_thread.start()
            
            # Start start-signal thread (only handles start signal based on ETA)
            print("Starting start-signal thread (ETA gating)...")
            signal_thread = threading.Thread(
                target=self._signal_gating_thread,
                args=()
            )
            signal_thread.start()

            # Start worker thread to send processed batches to the web page
            print("Starting frame worker thread (HTTP batch sender)...")
            self._worker_stop = False
            self._worker_frames_sent = 0
            self._worker_thread = threading.Thread(
                target=self._frame_worker_thread,
                args=() # Pass batch_size to the worker
            )
            self._worker_thread.start()
            
            # Wait for inference to complete
            print("Waiting for inference to complete...")
            inference_thread.join()
            print("Inference completed!")

            # Wait for start-signal thread to complete
            print("Waiting for start-signal thread to complete...")
            signal_thread.join()
            print("Start-signal thread completed!")

            # Stop buffer sender thread and wait for it to complete
            print("Stopping buffer sender thread...")
            self.buffer_sender_stop = True
            if self.buffer_sender_thread:
                self.buffer_sender_thread.join()
            print("Buffer sender thread completed!")

            # Wait for worker to flush remaining frames and send finish signal
            print("Waiting for frame worker to finish...")
            self._worker_thread.join()
            print("Frame worker completed!")

            # Verify all frames were sent
            print(f"=== Final Frame Count Verification ===")
            print(f"Frames generated by inference: {self.frame_count}")
            print(f"Frames expected: {self.total_frames_expected}")
            if hasattr(self, '_worker_frames_sent'):
                print(f"Frames sent by worker (legacy metric): {self._worker_frames_sent}")
            print(f"======================================")
            
            # Reset service state for next request
            self.reset_service_state()
            
            # Cleanup
            if get_file_type(video_path) == "video":
                import shutil
                shutil.rmtree(temp_dir)
            
            return {"status": "success", "frames_processed": self.frame_count}
            
        except Exception as e:
            print(f"Error in process_audio_with_video: {e}")
            self.processing = False
            self.inference_complete = True
            
            # Reset service state even on error
            try:
                self.reset_service_state()
            except Exception as reset_error:
                print(f"Error during service reset: {reset_error}")
            
            return {"status": "error", "message": str(e)}
    
    def _run_inference(self, whisper_chunks, input_latent_list_cycle, frame_list_cycle, coord_list_cycle, 
                      batch_size, extra_margin, parsing_mode):
        """Run inference in a separate thread using realtime.yaml configuration"""
        try:
            # Perform inference
            video_num = len(whisper_chunks)
            self.total_frames_expected = video_num  # Store expected frame count
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
                
                print(f"Inference: Processed batch {batch_count} with {frames_in_batch} frames (total in buffer: {len(self.frame_buffer)})")
                
                # Check if start condition is met and we haven't sent the initial buffer yet
                if (self.estimated_finish_time <= self.audio_duration and 
                    not self._start_signal_sent and 
                    len(self.frame_buffer) > 0):
                    
                    print(f"Inference: Start condition met! Queuing entire buffer ({len(self.frame_buffer)} frames)")
                    
                    # Queue entire buffer for sending (non-blocking)
                    self._queue_buffer_for_sending()
                    
                    # Mark start signal as sent
                    self._start_signal_sent = True
                
                # After start condition is met, send buffer every 2 batches
                elif (self._start_signal_sent and 
                      batch_count % 2 == 0 and 
                      len(self.frame_buffer) > 0):
                    
                    print(f"Inference: Queuing buffer after {batch_count} batches ({len(self.frame_buffer)} frames)")
                    self._queue_buffer_for_sending()
                
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
                print(f"  ---")
            
            # Store frame count for return value
            self.frame_count = frame_idx
            total_time = time.time() - start_time
            final_fps = frame_idx / total_time if total_time > 0 else 0

            print(f"=== Inference Complete ===")
            print(f"Total frames generated: {frame_idx}")
            print(f"Total frames expected: {self.total_frames_expected}")
            print(f"Frame deficit: {self.total_frames_expected - frame_idx}")
            print(f"Total time: {total_time:.2f}s")
            print(f"Final FPS: {final_fps:.2f}")
            print(f"==========================")

            # Set inference complete flag to signal worker thread
            self.inference_complete = True

        except Exception as e:
            print(f"Error in inference thread: {e}")
            self.processing = False
            self.inference_complete = True
            
            # Reset service state on inference error
            try:
                self.reset_service_state()
            except Exception as reset_error:
                print(f"Error during service reset after inference error: {reset_error}")
    
    def _signal_gating_thread(self):
        """Send the start signal over HTTP once ETA <= audio duration, and finished signal when complete."""
        print(f"=== Start Signal Thread ===")
        print(f"Waiting for estimated time to be <= audio duration...")
        
        # Wait for ETA to be <= audio duration
        while self.estimated_finish_time > self.audio_duration and not self.inference_complete:
            time.sleep(0.1)

        # Send start signal once when condition is met
        if not self._start_signal_sent:
            try:
                eft = self.estimated_finish_time
                if not math.isfinite(eft):
                    eft = None
                start_data = {
                    'status': 'start',
                    'estimated_finish_time': eft,
                    'audio_duration': self.audio_duration,
                    'timestamp': time.time(),
                    'message': 'Starting frame streaming - ETA <= audio duration'
                }
                response = requests.post(
                    self.stream_url,
                    json=start_data,
                    headers={'Content-Type': 'application/json'},
                    timeout=10
                )
                if response.status_code == 200:
                    print(f"  SUCCESS: Start signal sent (ETA: {eft:.2f}s <= Audio: {self.audio_duration:.2f}s)")
                    self._start_signal_sent = True
                    self._streaming_started = True
                else:
                    print(f"  ERROR: Failed to send start signal, status: {response.status_code}")
            except Exception as e:
                print(f"  ERROR sending start signal: {e}")
        
        # Wait for inference to complete
        print(f"Waiting for inference to complete...")
        while not self.inference_complete:
            time.sleep(0.1)
        
        # Queue any remaining frames in buffer
        if len(self.frame_buffer) > 0:
            print(f"Queuing final {len(self.frame_buffer)} frames from buffer")
            self._queue_buffer_for_sending()
        
        # Send finished signal once inference is complete
        if not self._finished_signal_sent:
            try:
                finished_data = {
                    'status': 'finished',
                    'total_frames_expected': self.total_frames_expected,
                    'frames_generated': self.frame_count,
                    'timestamp': time.time(),
                    'message': f'Inference completed successfully - {self.frame_count}/{self.total_frames_expected} frames generated'
                }
                response = requests.post(
                    self.stream_url,
                    json=finished_data,
                    headers={'Content-Type': 'application/json'},
                    timeout=5
                )
                if response.status_code == 200:
                    print(f"  SUCCESS: Sent finished signal")
                    self._finished_signal_sent = True
                else:
                    print(f"  ERROR: Failed to send finished signal, status: {response.status_code}")
            except Exception as e:
                print(f"  ERROR sending finished signal: {e}")
        
        print(f"=== Signal Thread Complete ===")

    def _frame_worker_thread(self):
        """Handle start signal and finished signal only - frames are sent directly from inference loop."""
        print("=== Frame Worker Thread Started ===")
        print("Worker thread will handle start signal and finished signal only")
        
        # Wait for inference to complete
        while not self.inference_complete:
            time.sleep(0.1)
        
        print("Inference completed, worker thread finishing...")
        print("=== Frame Worker Thread Complete ===")

    def _buffer_sender_thread(self):
        """Dedicated thread to send frames from the buffer queue without blocking inference."""
        print("=== Buffer Sender Thread Started ===")
        buffers_sent = 0
        
        # Create a session for connection pooling and faster requests
        import requests
        session = requests.Session()
        session.headers.update({'Content-Type': 'application/json'})
        
        while not self.buffer_sender_stop:
            try:
                # Get buffer from queue with timeout
                try:
                    buffer_data = self.buffer_queue.get(timeout=0.1)
                except queue.Empty:
                    # Check if inference is complete and queue is empty
                    if self.inference_complete and self.buffer_queue.empty():
                        break
                    continue
                
                # Send the buffer to the web page
                frames_to_send = buffer_data['frames']
                total_frames = buffer_data['total_frames']
                inference_complete = buffer_data['inference_complete']
                
                payload = {
                    'frames': frames_to_send,
                    'total_frames': total_frames,
                    'inference_complete': inference_complete
                }
                
                try:
                    # Use session for connection pooling and faster requests
                    resp = session.post(
                        self.stream_url,
                        json=payload,
                        timeout=5,
                        headers={'Content-Type': 'application/json'}
                    )
                    if resp.status_code == 200:
                        print(f"Sender: Successfully sent {len(frames_to_send)} frames")
                        buffers_sent += 1
                    else:
                        print(f"Sender: HTTP error sending buffer: status {resp.status_code}")
                except Exception as e:
                    print(f"Sender: Error sending buffer: {e}")
                
                # Mark task as done
                self.buffer_queue.task_done()
                
            except Exception as e:
                print(f"Sender: Unexpected error in buffer sender thread: {e}")
                time.sleep(0.1)
        
        # Close session
        session.close()
        print(f"=== Buffer Sender Thread Complete - Sent {buffers_sent} buffers ===")

    def _queue_buffer_for_sending(self):
        """Queue the current buffer for sending to the web page."""
        try:
            # Prepare frames for sending
            frames_to_send = []
            with self.buffer_lock:
                for frame_entry in self.frame_buffer:
                    frame_b64 = base64.b64encode(frame_entry['frame_data']).decode('utf-8')
                    frames_to_send.append({
                        'frame_number': frame_entry['frame_number'],
                        'frame_data': frame_b64
                    })
                # Clear the main buffer after preparing frames
                self.frame_buffer.clear()
            
            # Queue the frames for sending
            self.buffer_queue.put({
                'frames': frames_to_send,
                'total_frames': self.total_frames_expected,
                'inference_complete': False
            })
            print(f"Queued {len(frames_to_send)} frames for sending")
        except Exception as e:
            print(f"Error queuing buffer for sending: {e}")

    def reset_service_state(self):
        """Reset the service state to be ready for another request"""
        print("=== Resetting Service State ===")
        
        # Reset processing flags
        self.processing = False
        self.frame_count = 0
        self.inference_complete = False
        
        # Reset phase control
        self.phase1_complete = False
        self.phase2_active = False
        
        # Clear frame buffer
        with self.buffer_lock:
            self.frame_buffer.clear()
        
        # Clear buffer queue
        while not self.buffer_queue.empty():
            try:
                self.buffer_queue.get_nowait()
                self.buffer_queue.task_done()
            except queue.Empty:
                break
        
        # Reset buffer sender thread
        self.buffer_sender_stop = False
        self.buffer_sender_thread = None
        
        # Reset streaming control
        self.estimated_finish_time = float('inf')
        self.audio_duration = 0
        self.stream_url = None
        self.total_frames_expected = 0
        self._worker_frames_sent = 0
        
        # Reset WebRTC components
        self.webrtc_read_index = 0
        self._start_signal_sent = False
        self._finished_signal_sent = False
        self._streaming_started = False
        
        # Reset worker thread
        self._worker_stop = False
        
        print("Service state reset complete - ready for next request")
        print("================================================")

    def is_ready_for_request(self):
        """Check if the service is ready to accept a new request"""
        return not self.processing and not self.inference_complete and len(self.frame_buffer) == 0


class MuseVideoTrack(MediaStreamTrack):
    kind = "video"

    def __init__(self, service: MuseTalkService):
        super().__init__()
        self.service = service
        self._last_pts = 0
        self._time_base = fractions.Fraction(1, max(1, int(service.fps)))

    async def recv(self) -> VideoFrame:
        # Wait until start condition is met, only once
        if not self.service._streaming_started:
            while self.service.estimated_finish_time > self.service.audio_duration and not self.service.inference_complete:
                await asyncio.sleep(0.02)
            self.service._streaming_started = True

        # Wait for next frame to be available in buffer
        frame_bytes = None
        while frame_bytes is None:
            with self.service.buffer_lock:
                if self.service.webrtc_read_index < len(self.service.frame_buffer):
                    frame_entry = self.service.frame_buffer[self.service.webrtc_read_index]
                    frame_bytes = frame_entry['frame_data']
                    self.service.webrtc_read_index += 1
                else:
                    frame_bytes = None
            if frame_bytes is None:
                # If inference is complete and no more frames expected, hold on last frame pace
                if self.service.inference_complete and self.service.webrtc_read_index >= self.service.total_frames_expected:
                    await asyncio.sleep(1.0 / max(1, int(self.service.fps)))
                else:
                    await asyncio.sleep(0.005)

        # Decode JPEG bytes to BGR image
        np_arr = np.frombuffer(frame_bytes, dtype=np.uint8)
        img_bgr = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
        if img_bgr is None:
            # Fallback to a blank frame if decoding fails
            img_bgr = np.zeros((256, 256, 3), dtype=np.uint8)

        frame = VideoFrame.from_ndarray(img_bgr, format='bgr24')
        self._last_pts += 1
        frame.pts = self._last_pts
        frame.time_base = self._time_base
        return frame

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
    
    # Check if service is ready for a new request
    if not service.is_ready_for_request():
        return jsonify({
            "error": "Service is currently processing another request. Please wait for it to complete."
        }), 409  # Conflict status code
    
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
        "ready_for_request": service.is_ready_for_request(),
        "buffer_size": len(service.frame_buffer),
        "phase1_complete": service.phase1_complete,
        "phase2_active": service.phase2_active,
        "estimated_finish_time": service.estimated_finish_time if math.isfinite(service.estimated_finish_time) else None,
        "audio_duration": service.audio_duration,
        "webrtc_read_index": service.webrtc_read_index if service else 0
    })

@app.route('/webrtc_offer', methods=['POST'])
def webrtc_offer():
    """Accept a WebRTC SDP offer and return an answer. Adds a video track that streams generated frames."""
    global service
    if service is None:
        return jsonify({"error": "Service not initialized"}), 500

    try:
        data = request.get_json(force=True)
        sdp = data.get('sdp')
        type_ = data.get('type')
        if not sdp or not type_:
            return jsonify({"error": "Invalid SDP offer"}), 400

        async def handle_offer():
            # Close previous connection if any
            if service.webrtc_pc is not None:
                try:
                    await service.webrtc_pc.close()
                except Exception:
                    pass

            pc = RTCPeerConnection()
            service.webrtc_pc = pc

            # Add video track
            service.webrtc_track = MuseVideoTrack(service)
            pc.addTrack(service.webrtc_track)

            @pc.on("connectionstatechange")
            async def on_state_change():
                print(f"WebRTC connection state: {pc.connectionState}")
                if pc.connectionState in ("failed", "closed", "disconnected"):
                    try:
                        await pc.close()
                    except Exception:
                        pass

            offer = RTCSessionDescription(sdp=sdp, type=type_)
            await pc.setRemoteDescription(offer)
            answer = await pc.createAnswer()
            await pc.setLocalDescription(answer)
            return {"sdp": pc.localDescription.sdp, "type": pc.localDescription.type}

        future = asyncio.run_coroutine_threadsafe(handle_offer(), service._aio_loop)
        answer_payload = future.result(timeout=10)
        return jsonify(answer_payload)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/mjpeg_stream', methods=['GET'])
def mjpeg_stream():
    """Serve frames as an MJPEG multipart stream, starting only after start condition."""
    global service
    if service is None:
        return jsonify({"error": "Service not initialized"}), 500

    boundary = b'--frame\r\n'

    def generate_stream():
        # Wait until start condition is met
        while service.estimated_finish_time > service.audio_duration and not service.inference_complete:
            time.sleep(0.05)

        # Ensure we start from the first frame
        read_index = 0

        # Wait for first frame to be available
        initial_wait = 0
        while True:
            with service.buffer_lock:
                if len(service.frame_buffer) > 0:
                    break
            if service.inference_complete:
                break
            time.sleep(0.02)
            initial_wait += 1
            if initial_wait % 100 == 0:
                print(f"MJPEG waiting for first frame... {initial_wait*0.02:.1f}s")

        # Stream frames as they arrive
        while True:
            frame_bytes = None
            with service.buffer_lock:
                if read_index < len(service.frame_buffer):
                    entry = service.frame_buffer[read_index]
                    frame_bytes = entry['frame_data']
                    read_index += 1

            if frame_bytes is not None:
                try:
                    yield boundary
                    yield b'Content-Type: image/jpeg\r\n'
                    yield f'Content-Length: {len(frame_bytes)}\r\n\r\n'.encode('utf-8')
                    yield frame_bytes
                    yield b'\r\n'
                except GeneratorExit:
                    break
                except Exception as e:
                    print(f"MJPEG stream write error: {e}")
                    break
            else:
                # No new frame yet
                if service.inference_complete and read_index >= service.total_frames_expected:
                    # End of stream
                    break
                time.sleep(0.01)

        # End boundary (optional)
        try:
            yield b'--frame--\r\n'
        except Exception:
            pass

    return Response(generate_stream(), mimetype='multipart/x-mixed-replace; boundary=frame')

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
