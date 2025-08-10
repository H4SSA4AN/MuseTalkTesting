"""
Avatar management for MuseTalk streaming server
"""

import sys
import os
import librosa

import av
import cv2
import numpy as np
import torch
import threading
import queue
from typing import List, Optional

from transformers import WhisperModel

from musetalk.utils.audio_processor import AudioProcessor
from musetalk.utils.preprocessing import get_landmark_and_bbox
from musetalk.utils.blending import get_image_blending, get_image_prepare_material
from musetalk.utils.face_parsing import FaceParsing
from musetalk.utils.utils import load_all_model, datagen

try:
    from .config import AVATAR_CONFIG, AUDIO_CONFIG
except ImportError:
    # Fallback for direct script execution
    from config import AVATAR_CONFIG, AUDIO_CONFIG


class CustomAvatar:
    def __init__(
        self,
        avatar_id: str,
        video_path: str,
        bbox_shift: int,
        batch_size: int,
        preparation: bool,
        fps: int = 25,
        vae_type: str = "sd-vae",
        unet_config: str = "./models/musetalk/musetalk.json",
        unet_model_path: str = "./models/musetalk/pytorch_model.bin",
        whisper_dir: str = "./models/whisper",
        extra_margin: int = 10,
        parsing_mode: str = "jaw",
        left_cheek_width: int = 90,
        right_cheek_width: int = 90,
        audio_padding_length_left: int = 2,
        audio_padding_length_right: int = 2,
        skip_save_images: bool = True,
        gpu_id: int = 0,
    ) -> None:
        self.avatar_id = avatar_id
        self.video_path = video_path
        self.bbox_shift = bbox_shift
        self.batch_size = batch_size
        self.preparation = preparation
        self.fps = fps
        self.skip_save_images = skip_save_images
        self.audio_padding_length_left = audio_padding_length_left
        self.audio_padding_length_right = audio_padding_length_right

        # Placeholder for the dynamic callback
        self.process_frames = None
        
        # device and models
        self.device = torch.device(f"cuda:{gpu_id}" if torch.cuda.is_available() else "cpu")
        self.vae, self.unet, self.pe = load_all_model(
            unet_model_path=unet_model_path,
            vae_type=vae_type,
            unet_config=unet_config,
            device=self.device,
        )
        self.timesteps = torch.tensor([0], device=self.device)

        # half precision
        self.pe = self.pe.half().to(self.device)
        self.vae.vae = self.vae.vae.half().to(self.device)
        self.unet.model = self.unet.model.half().to(self.device)
        self.weight_dtype = self.unet.model.dtype

        # audio/whisper
        self.audio_processor = AudioProcessor(feature_extractor_path=whisper_dir)
        self.whisper: WhisperModel = WhisperModel.from_pretrained(whisper_dir)
        self.whisper = self.whisper.to(device=self.device, dtype=self.weight_dtype).eval()
        self.whisper.requires_grad_(False)

        # face parsing
        self.fp = FaceParsing(left_cheek_width=left_cheek_width, right_cheek_width=right_cheek_width)
        self.parsing_mode = parsing_mode
        self.extra_margin = extra_margin

        # prepared materials
        self.frame_list_cycle: List[np.ndarray] = []
        self.coord_list_cycle: List[List[int]] = []
        self.mask_list_cycle: List[np.ndarray] = []
        self.mask_coords_list_cycle: List[List[int]] = []
        self.input_latent_list_cycle: List[torch.Tensor] = []
        self.idx = 0

        self._prepare_materials()

    def _prepare_materials(self) -> None:
        if os.path.isfile(self.video_path):
            temp_dir = os.path.join(os.path.dirname(__file__), "..", "results", "temp_avatar_frames")
            temp_dir = os.path.normpath(temp_dir)
            os.makedirs(temp_dir, exist_ok=True)
            for f in os.listdir(temp_dir):
                try:
                    os.remove(os.path.join(temp_dir, f))
                except Exception:
                    pass
            reader = av.open(self.video_path)
            stream = reader.streams.video[0]
            idx = 0
            for frame in reader.decode(stream):
                img = frame.to_ndarray(format="bgr24")
                out_path = os.path.join(temp_dir, f"{idx:08d}.png")
                cv2.imwrite(out_path, img)
                idx += 1
            input_img_paths = sorted(
                [os.path.join(temp_dir, p) for p in os.listdir(temp_dir) if p.lower().endswith((".png", ".jpg", ".jpeg"))]
            )
        else:
            input_img_paths = sorted(
                [os.path.join(self.video_path, p) for p in os.listdir(self.video_path) if p.lower().endswith((".png", ".jpg", ".jpeg"))]
            )

        coord_list, frame_list = get_landmark_and_bbox(input_img_paths, self.bbox_shift)

        input_latent_list: List[torch.Tensor] = []
        for bbox, frame in zip(coord_list, frame_list):
            # Convert bbox to list/tuple if it's a tensor to avoid boolean ambiguity
            if isinstance(bbox, torch.Tensor):
                bbox = bbox.tolist()
            if bbox == [0.0, 0.0, 0.0, 0.0] or bbox == (0.0, 0.0, 0.0, 0.0):
                continue
            x1, y1, x2, y2 = bbox
            y2 = min(y2 + self.extra_margin, frame.shape[0])
            crop_frame = frame[y1:y2, x1:x2]
            resized_crop_frame = cv2.resize(crop_frame, (256, 256), interpolation=cv2.INTER_LANCZOS4)
            latents = self.vae.get_latents_for_unet(resized_crop_frame)
            input_latent_list.append(latents)

        self.frame_list_cycle = frame_list + frame_list[::-1]
        self.coord_list_cycle = coord_list + coord_list[::-1]
        self.input_latent_list_cycle = input_latent_list + input_latent_list[::-1]

        self.mask_list_cycle = []
        self.mask_coords_list_cycle = []
        for i, frame in enumerate(self.frame_list_cycle):
            x1, y1, x2, y2 = self.coord_list_cycle[i]
            mask, crop_box = get_image_prepare_material(frame, [x1, y1, x2, y2], fp=self.fp, mode=self.parsing_mode)
            self.mask_list_cycle.append(mask)
            self.mask_coords_list_cycle.append(crop_box)

    def inference(self, audio_path: str, out_vid_name: Optional[str], fps: int, skip_save_images: bool, batch_size: int = 16, frame_queue: queue.Queue = None):
        if not os.path.exists(audio_path):
            print(f"Error: Audio file not found: {audio_path}")
            return
        
        print(f"Processing audio file: {audio_path}")
        
        audio_result = self.audio_processor.get_audio_feature(
            audio_path, weight_dtype=self.weight_dtype
        )
        
        if audio_result is None:
            print(f"Error: Could not extract audio features from {audio_path}")
            return
        
        whisper_input_features, librosa_length = audio_result
        print(f"Audio features extracted successfully. Length: {librosa_length:.2f}s")
        
        whisper_chunks = self.audio_processor.get_whisper_chunk(
            whisper_input_features,
            self.device,
            self.weight_dtype,
            self.whisper,
            librosa_length,
            fps=fps,
            audio_padding_length_left=self.audio_padding_length_left,
            audio_padding_length_right=self.audio_padding_length_right,
        )
        
        if whisper_chunks is None or len(whisper_chunks) == 0:
            print(f"Error: No whisper chunks generated from audio")
            # Put sentinel value to terminate processor thread
            frame_queue.put(None)
            return
        
        video_num = len(whisper_chunks)
        print(f"Generated {video_num} video frames from audio chunks")

        # Direct generation loop, producing raw frames for the pipeline
        gen = datagen(
            whisper_chunks,
            self.input_latent_list_cycle,
            batch_size=batch_size,
        )

        for _, (whisper_batch, latent_batch) in enumerate(gen):
            audio_feature_batch = self.pe(whisper_batch.to(self.device))
            latent_batch = latent_batch.to(device=self.device, dtype=self.unet.model.dtype)
            
            pred_latents = self.unet.model(
                latent_batch, self.timesteps, encoder_hidden_states=audio_feature_batch
            ).sample
            
            pred_latents = pred_latents.to(device=self.device, dtype=self.vae.vae.dtype)
            recon = self.vae.decode_latents(pred_latents)
            
            # Put the raw, unprocessed batch into the queue for the processor thread
            frame_queue.put(recon)

        # Signal completion to the processor thread
        frame_queue.put(None)


def _build_custom_avatar():
    """Build a custom avatar with hardcoded parameters"""
    return CustomAvatar(
        avatar_id=AVATAR_CONFIG["avatar_id"],
        video_path=AVATAR_CONFIG["video_path"],
        bbox_shift=AVATAR_CONFIG["bbox_shift"],
        batch_size=AVATAR_CONFIG["batch_size"],
        preparation=AVATAR_CONFIG["preparation"],
        fps=AVATAR_CONFIG.get("fps", 25),
        vae_type=AVATAR_CONFIG.get("vae_type", "sd-vae"),
        unet_config=AVATAR_CONFIG.get("unet_config", "./models/musetalk/musetalk.json"),
        unet_model_path=AVATAR_CONFIG.get("unet_model_path", "./models/musetalk/pytorch_model.bin"),
        whisper_dir=AVATAR_CONFIG.get("whisper_dir", "./models/whisper"),
        extra_margin=AVATAR_CONFIG.get("extra_margin", 10),
        parsing_mode=AVATAR_CONFIG.get("parsing_mode", "jaw"),
        left_cheek_width=AVATAR_CONFIG.get("left_cheek_width", 90),
        right_cheek_width=AVATAR_CONFIG.get("right_cheek_width", 90),
        audio_padding_length_left=AVATAR_CONFIG.get("audio_padding_length_left", 2),
        audio_padding_length_right=AVATAR_CONFIG.get("audio_padding_length_right", 2),
        skip_save_images=AVATAR_CONFIG.get("skip_save_images", True),
        gpu_id=AVATAR_CONFIG.get("gpu_id", 0),
    )


class AvatarManager:
    """Manages avatar initialization and configuration"""
    
    def __init__(self):
        self.avatar = None
        self.avatar_fps = AVATAR_CONFIG["fps"]
        self.batch_size = AVATAR_CONFIG["batch_size"]
        self.ready = False
        self._skip_save_images = AVATAR_CONFIG.get("skip_save_images", True)
    
    def initialize(self):
        """Initialize the avatar with all required components"""
        print("Pre-initializing MuseTalk avatar...")
        
        try:
            # Build a minimal custom avatar inline (no args dependency)
            self.avatar = _build_custom_avatar()
            
            # Update fps and batch_size values
            self.avatar_fps = self.avatar.fps
            self.batch_size = self.avatar.batch_size
            print(f"Avatar FPS set to: {self.avatar_fps}, Batch size: {self.batch_size}")
            
            print("Avatar pre-initialization complete!")
            self.ready = True
            
        except Exception as e:
            print(f"Error pre-initializing avatar: {e}")
            self.ready = False
    
    def is_ready(self) -> bool:
        """Check if avatar is ready for inference"""
        return self.ready and self.avatar is not None
    
    def get_avatar(self):
        """Get the initialized avatar instance"""
        return self.avatar
    
    def get_fps(self) -> int:
        """Get avatar FPS"""
        return self.avatar_fps

    def set_fps(self, fps: int):
        """Set avatar FPS"""
        self.avatar_fps = fps
        if self.avatar:
            self.avatar.fps = fps

    def get_batch_size(self) -> int:
        """Get batch size"""
        return self.batch_size
    
    def set_batch_size(self, batch_size: int):
        """Set batch size"""
        self.batch_size = batch_size
        if self.avatar:
            self.avatar.batch_size = batch_size

    def get_skip_save_images(self) -> bool:
        """Get skip_save_images setting"""
        return self._skip_save_images
    
    def get_audio_path(self) -> str:
        """Get audio file path"""
        return AUDIO_CONFIG["audio_path"] 