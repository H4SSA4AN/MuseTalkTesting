import os
import sys
import time
import json
import tempfile
import threading
import queue
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
        self.frame_queue = queue.Queue()
        self.processing = False
        self.frame_count = 0
        
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
    
    def process_audio_with_video(self, audio_path: str, video_path: str, 
                                stream_url: str, bbox_shift: int = 0) -> Dict[str, Any]:
        """Process audio with video and stream frames to specified URL using realtime.yaml config"""
        try:
            # Load realtime.yaml configuration
            inference_config = OmegaConf.load(self.config_path)
            print(f"Using inference config: {inference_config}")
            
            # Get default parameters from realtime_inference.py
            fps = 25  # Default FPS for realtime inference
            audio_padding_length_left = 2
            audio_padding_length_right = 2
            batch_size = 20  # Default batch size for realtime inference
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
            print(f"Audio features extracted. Librosa length: {librosa_length}")
            
            # Get video FPS if it's a video file
            if get_file_type(video_path) == "video":
                fps = get_video_fps(video_path)
                print(f"Video FPS detected: {fps}")
            
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
            
            # Start inference thread
            print("Starting inference and streaming threads...")
            self.processing = True
            inference_thread = threading.Thread(
                target=self._run_inference,
                args=(whisper_chunks, input_latent_list_cycle, frame_list_cycle, coord_list_cycle, 
                      batch_size, extra_margin, parsing_mode)
            )
            inference_thread.start()
            
            # Start streaming thread
            stream_thread = threading.Thread(
                target=self._stream_frames,
                args=(stream_url,)
            )
            stream_thread.start()
            
            # Wait for inference to complete
            print("Waiting for inference to complete...")
            inference_thread.join()
            print("Inference completed!")
            
            # Wait for streaming to complete
            print("Waiting for streaming to complete...")
            self.processing = False
            stream_thread.join()
            print("Streaming completed!")
            
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
                    
                    # Add to queue for streaming
                    self.frame_queue.put((frame_idx, combine_frame))
                    frame_idx += 1
                    frames_in_batch += 1
                
                batch_time = time.time() - batch_start_time
                elapsed_time = time.time() - start_time
                avg_fps = frame_idx / elapsed_time if elapsed_time > 0 else 0
                
                print(f"  Batch completed in {batch_time:.2f}s")
                print(f"  Frames in this batch: {frames_in_batch}")
                print(f"  Total frames processed: {frame_idx}/{video_num}")
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
    
    def _stream_frames(self, stream_url: str):
        """Stream frames to the specified URL"""
        frame_idx = 0
        start_time = time.time()
        last_log_time = start_time
        
        print(f"=== Starting Frame Streaming ===")
        print(f"Stream URL: {stream_url}")
        print(f"===============================")
        
        while self.processing or not self.frame_queue.empty():
            try:
                if self.frame_queue.empty():
                    time.sleep(0.01)
                    continue
                
                idx, frame = self.frame_queue.get(timeout=1)
                
                # Encode frame as JPEG
                _, buffer = cv2.imencode('.jpg', frame)
                frame_data = buffer.tobytes()
                
                # Send frame to stream URL
                try:
                    response = requests.post(
                        stream_url,
                        data=frame_data,
                        headers={'Content-Type': 'image/jpeg', 'Frame-Index': str(idx)},
                        timeout=5
                    )
                    if response.status_code != 200:
                        print(f"Warning: Failed to stream frame {idx}, status: {response.status_code}")
                except Exception as e:
                    print(f"Error streaming frame {idx}: {e}")
                
                frame_idx += 1
                
                # Log progress every 50 frames or every 2 seconds
                current_time = time.time()
                if frame_idx % 50 == 0 or (current_time - last_log_time) >= 2.0:
                    elapsed_time = current_time - start_time
                    streaming_fps = frame_idx / elapsed_time if elapsed_time > 0 else 0
                    print(f"Streamed {frame_idx} frames (FPS: {streaming_fps:.2f})")
                    last_log_time = current_time
                
            except queue.Empty:
                continue
            except Exception as e:
                print(f"Error in streaming thread: {e}")
                break
        
        total_time = time.time() - start_time
        final_streaming_fps = frame_idx / total_time if total_time > 0 else 0
        
        print(f"=== Streaming Complete ===")
        print(f"Total frames streamed: {frame_idx}")
        print(f"Total streaming time: {total_time:.2f}s")
        print(f"Final streaming FPS: {final_streaming_fps:.2f}")
        print(f"==========================")

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
        video_path = request.form.get('video_path')
        stream_url = request.form.get('stream_url')
        bbox_shift = int(request.form.get('bbox_shift', 0))
        
        if not video_path or not stream_url:
            return jsonify({"error": "video_path and stream_url are required"}), 400
        
        # Save audio file to inputs folder
        saved_audio_path = service.save_audio_to_inputs(audio_file, audio_file.filename)
        
        try:
            # Start processing in background thread
            processing_thread = threading.Thread(
                target=service.process_audio_with_video,
                args=(saved_audio_path, video_path, stream_url, bbox_shift)
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
        "queue_size": service.frame_queue.qsize()
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
