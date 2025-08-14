import asyncio
import json
import os
import time
from typing import Optional, Tuple, List

import av
import cv2
import numpy as np
import torch
import threading
import queue
import subprocess
import sys
import shutil
from aiohttp import web
from aiortc import RTCPeerConnection, RTCSessionDescription, MediaStreamTrack
from aiortc.contrib.media import MediaBlackhole
from av import VideoFrame
from omegaconf import OmegaConf
from transformers import WhisperModel
from fractions import Fraction
import pathlib

# Import enhanced CORS
try:
    from webrtc.enhanced_cors import create_simple_cors_middleware
except ImportError:
    # Fallback for direct script execution
    from enhanced_cors import create_simple_cors_middleware

# MuseTalk imports
from musetalk.utils.audio_processor import AudioProcessor
from musetalk.utils.blending import get_image_blending, get_image_prepare_material
from musetalk.utils.face_parsing import FaceParsing
from musetalk.utils.preprocessing import get_landmark_and_bbox, read_imgs
from musetalk.utils.utils import datagen, load_all_model
from musetalk.utils.file_handler import FileHandler, FileWatcher


class MuseTalkRealtimeEngine:
    """Real-time MuseTalk inference engine that yields combined video frames for WebRTC.

    This class prepares an avatar (preprocess frames, landmarks, latents, masks), then
    given an audio file path, performs incremental inference and yields combined frames.
    """

    def __init__(
        self,
        version: str = "v15",
        gpu_id: int = 0,
        vae_type: str = "sd-vae",
        unet_config: str = "./models/musetalk/musetalk.json",
        unet_model_path: str = "./models/musetalk/pytorch_model.bin",
        whisper_dir: str = "./models/whisper",
        extra_margin: int = 10,
        parsing_mode: str = "jaw",
        left_cheek_width: int = 90,
        right_cheek_width: int = 90,
    ) -> None:
        self.version = version
        self.device = torch.device(f"cuda:{gpu_id}" if torch.cuda.is_available() else "cpu")

        # Load models (aligned with scripts/realtime_inference.py)
        self.vae, self.unet, self.pe = load_all_model(
            unet_model_path=unet_model_path,
            vae_type=vae_type,
            unet_config=unet_config,
            device=self.device,
        )
        self.timesteps = torch.tensor([0], device=self.device)

        # Use float16 where possible
        self.pe = self.pe.half().to(self.device)
        self.vae.vae = self.vae.vae.half().to(self.device)
        self.unet.model = self.unet.model.half().to(self.device)
        self.weight_dtype = self.unet.model.dtype

        self.audio_processor = AudioProcessor(feature_extractor_path=whisper_dir)
        self.whisper: WhisperModel = WhisperModel.from_pretrained(whisper_dir)
        self.whisper = self.whisper.to(device=self.device, dtype=self.weight_dtype).eval()
        self.whisper.requires_grad_(False)

        # Face parsing (v15 supports parsing parameters)
        if self.version == "v15":
            self.fp = FaceParsing(
                left_cheek_width=left_cheek_width,
                right_cheek_width=right_cheek_width,
            )
        else:
            self.fp = FaceParsing()

        self.extra_margin = extra_margin
        self.parsing_mode = parsing_mode

        # Prepared avatar state
        self.frame_list_cycle: List[np.ndarray] = []
        self.coord_list_cycle: List[List[int]] = []
        self.mask_list_cycle: List[np.ndarray] = []
        self.mask_coords_list_cycle: List[List[int]] = []
        self.input_latent_list_cycle: List[torch.Tensor] = []

    def _prepare_materials(self, video_path: str, bbox_shift: int) -> None:
        # Build list of image file paths
        if os.path.isfile(video_path):
            # Extract frames to a temporary folder of images
            temp_dir = os.path.join(os.path.dirname(__file__), "results", "temp_avatar_frames")
            os.makedirs(temp_dir, exist_ok=True)
            # Clear previous
            for f in os.listdir(temp_dir):
                try:
                    os.remove(os.path.join(temp_dir, f))
                except Exception:
                    pass
            reader = av.open(video_path)
            stream = reader.streams.video[0]
            idx = 0
            for frame in reader.decode(stream):
                img = frame.to_ndarray(format="bgr24")
                out_path = os.path.join(temp_dir, f"{idx:08d}.png")
                cv2.imwrite(out_path, img)
                idx += 1
            input_img_paths = sorted([os.path.join(temp_dir, p) for p in os.listdir(temp_dir) if p.lower().endswith((".png", ".jpg", ".jpeg"))])
        else:
            input_img_paths = sorted([os.path.join(video_path, p) for p in os.listdir(video_path) if p.lower().endswith((".png", ".jpg", ".jpeg"))])

        # Landmarks and bboxes
        coord_list, frame_list = get_landmark_and_bbox(input_img_paths, bbox_shift)

        # Compute latents per face crop
        input_latent_list: List[torch.Tensor] = []
        for bbox, frame in zip(coord_list, frame_list):
            # coord_placeholder is handled in the utils, ignore empty bboxes
            if bbox == (0.0, 0.0, 0.0, 0.0):
                continue
            x1, y1, x2, y2 = bbox
            if self.version == "v15":
                y2 = y2 + self.extra_margin
                y2 = min(y2, frame.shape[0])
            crop_frame = frame[y1:y2, x1:x2]
            resized_crop_frame = cv2.resize(crop_frame, (256, 256), interpolation=cv2.INTER_LANCZOS4)
            latents = self.vae.get_latents_for_unet(resized_crop_frame)
            input_latent_list.append(latents)

        # To smooth first and last frames
        self.frame_list_cycle = frame_list + frame_list[::-1]
        self.coord_list_cycle = coord_list + coord_list[::-1]
        self.input_latent_list_cycle = input_latent_list + input_latent_list[::-1]

        # Build masks for blending (use parsing-based masks as in scripts)
        self.mask_list_cycle = []
        self.mask_coords_list_cycle = []
        for i, frame in enumerate(self.frame_list_cycle):
            x1, y1, x2, y2 = self.coord_list_cycle[i]
            mode = self.parsing_mode if self.version == "v15" else "raw"
            mask, crop_box = get_image_prepare_material(frame, [x1, y1, x2, y2], fp=self.fp, mode=mode)
            self.mask_list_cycle.append(mask)
            self.mask_coords_list_cycle.append(crop_box)

    def prepare_avatar(self, video_path: str, bbox_shift: int = 0) -> None:
        self._prepare_materials(video_path=video_path, bbox_shift=bbox_shift)

    def frames_from_audio(self, audio_path: str, fps: int = 25):
        # Extract audio features and chunk to whisper frame rate
        whisper_input_features, librosa_length = self.audio_processor.get_audio_feature(
            audio_path, weight_dtype=self.weight_dtype
        )
        whisper_chunks = self.audio_processor.get_whisper_chunk(
            whisper_input_features,
            self.device,
            self.weight_dtype,
            self.whisper,
            librosa_length,
            fps=fps,
            audio_padding_length_left=2,
            audio_padding_length_right=2,
        )

        video_num = len(whisper_chunks)
        gen = datagen(
            whisper_chunks,
            self.input_latent_list_cycle,
            batch_size=20,
        )

        idx = 0
        for _, (whisper_batch, latent_batch) in enumerate(gen):
            audio_feature_batch = self.pe(whisper_batch.to(self.device))
            latent_batch = latent_batch.to(device=self.device, dtype=self.unet.model.dtype)

            pred_latents = self.unet.model(
                latent_batch, self.timesteps, encoder_hidden_states=audio_feature_batch
            ).sample
            pred_latents = pred_latents.to(device=self.device, dtype=self.vae.vae.dtype)
            recon = self.vae.decode_latents(pred_latents)

            for res_frame in recon:
                # Compose into original frame via blending
                bbox = self.coord_list_cycle[idx % len(self.coord_list_cycle)]
                ori_frame = np.copy(self.frame_list_cycle[idx % len(self.frame_list_cycle)])
                x1, y1, x2, y2 = bbox
                try:
                    res_frame = cv2.resize(res_frame.astype(np.uint8), (x2 - x1, y2 - y1))
                except Exception:
                    idx += 1
                    continue
                mask = self.mask_list_cycle[idx % len(self.mask_list_cycle)]
                mask_crop_box = self.mask_coords_list_cycle[idx % len(self.mask_coords_list_cycle)]

                combined = get_image_blending(ori_frame, res_frame, bbox, mask, mask_crop_box)
                yield combined
                idx += 1


class Avatar:
    """Avatar class for WebRTC streaming, mirroring realtime Avatar behavior.

    - Copies process_frames to a yielding variant
    - Provides inference() that starts generation and yields composed frames
    """

    def __init__(self, engine: MuseTalkRealtimeEngine, batch_size: int = 20) -> None:
        self.engine = engine
        self.batch_size = batch_size
        # Prepared materials
        self.frame_list_cycle = engine.frame_list_cycle
        self.coord_list_cycle = engine.coord_list_cycle
        self.mask_list_cycle = engine.mask_list_cycle
        self.mask_coords_list_cycle = engine.mask_coords_list_cycle
        self.input_latent_list_cycle = engine.input_latent_list_cycle
        self.idx = 0

    def process_frames_yield(self, res_frame_queue: "queue.Queue", video_len: int, skip_save_images: bool = True):
        self.idx = 0
        while True:
            if self.idx >= video_len - 1:
                break
            try:
                res_frame = res_frame_queue.get(block=True, timeout=1)
            except queue.Empty:
                continue
            if res_frame is None:
                break
            bbox = self.coord_list_cycle[self.idx % (len(self.coord_list_cycle))]
            ori_frame = np.copy(self.frame_list_cycle[self.idx % (len(self.frame_list_cycle))])
            x1, y1, x2, y2 = bbox
            try:
                res_frame = cv2.resize(res_frame.astype(np.uint8), (x2 - x1, y2 - y1))
            except Exception:
                self.idx += 1
                continue
            mask = self.mask_list_cycle[self.idx % (len(self.mask_list_cycle))]
            mask_crop_box = self.mask_coords_list_cycle[self.idx % (len(self.mask_coords_list_cycle))]
            combine_frame = get_image_blending(ori_frame, res_frame, bbox, mask, mask_crop_box)
            yield combine_frame
            self.idx += 1

    def inference(self, audio_path: str, fps: int = 25):
        print(f"[MuseTalk] Starting inference for audio: {audio_path}")
        # Extract audio features
        whisper_input_features, librosa_length = self.engine.audio_processor.get_audio_feature(
            audio_path, weight_dtype=self.engine.weight_dtype
        )
        print(f"[MuseTalk] Audio feature extracted. librosa_length={librosa_length}")
        whisper_chunks = self.engine.audio_processor.get_whisper_chunk(
            whisper_input_features,
            self.engine.device,
            self.engine.weight_dtype,
            self.engine.whisper,
            librosa_length,
            fps=fps,
            audio_padding_length_left=2,
            audio_padding_length_right=2,
        )
        print(f"[MuseTalk] Prepared {len(whisper_chunks)} whisper chunks at fps={fps}")
        video_num = len(whisper_chunks)
        res_frame_queue: queue.Queue = queue.Queue()

        def producer():
            gen = datagen(
                whisper_chunks,
                self.input_latent_list_cycle,
                batch_size=self.batch_size,
            )
            for _, (whisper_batch, latent_batch) in enumerate(gen):
                audio_feature_batch = self.engine.pe(whisper_batch.to(self.engine.device))
                latent_batch = latent_batch.to(device=self.engine.device, dtype=self.engine.unet.model.dtype)
                pred_latents = self.engine.unet.model(
                    latent_batch, self.engine.timesteps, encoder_hidden_states=audio_feature_batch
                ).sample
                pred_latents = pred_latents.to(device=self.engine.device, dtype=self.engine.vae.vae.dtype)
                recon = self.engine.vae.decode_latents(pred_latents)
                print(f"[MuseTalk] Generated {recon.shape[0]} frames in this batch")
                for res_frame in recon:
                    res_frame_queue.put(res_frame)
            res_frame_queue.put(None)

        thread = threading.Thread(target=producer, daemon=True)
        thread.start()

        for frame in self.process_frames_yield(res_frame_queue, video_len=video_num, skip_save_images=True):
            yield frame
        thread.join()


class MuseTalkVideoTrack(MediaStreamTrack):
    kind = "video"

    def __init__(self, frame_queue: "asyncio.Queue[VideoFrame]", fps: int = 25):
        super().__init__()
        self.queue = frame_queue
        self.frame_interval = 1.0 / max(1, fps)
        self._pts = 0
        # time_base as 1/fps
        self._time_base = Fraction(1, max(1, fps))

    async def recv(self) -> VideoFrame:
        start = time.time()
        frame = await self.queue.get()
        # Pace to target FPS
        now = time.time()
        wait = self.frame_interval - (now - start)
        if wait > 0:
            await asyncio.sleep(wait)
        # Assign monotonically increasing pts and proper time_base
        frame.pts = self._pts
        frame.time_base = self._time_base
        self._pts += 1
        return frame


class MuseTalkWebRTCServer:
    def __init__(
        self,
        avatar_video_path: Optional[str] = None,
        bbox_shift: Optional[int] = None,
        fps: int = 25,
    ) -> None:
        self.fps = fps
        self.answer_wav_path = None
        
        # Initialize improved file handling
        self._base_dir = os.path.dirname(__file__)
        self.file_handler = FileHandler(self._base_dir, "answers")
        
        # Verify permissions on startup
        if not self.file_handler.check_permissions():
            raise RuntimeError("Cannot access answers directory - check permissions")
        
        # Clear answers folder on startup
        self.file_handler.clear_directory()
        print(f"[MuseTalk] Cleared answers directory: {self.file_handler.answers_dir}")
        
        # New-answer signal
        self.answer_event: asyncio.Event = asyncio.Event()
        self.latest_answer_path: Optional[str] = None
        
        # Improved file watcher
        self._file_watcher: Optional[FileWatcher] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._rt_proc: Optional[subprocess.Popen] = None  # deprecated external run
        self._warm_infer_thread: Optional[threading.Thread] = None

        # Read realtime.yaml to configure avatar and audio path
        self.avatar_video_path, self.bbox_shift, self.config_audio_path = _load_realtime_config_defaults(avatar_video_path, bbox_shift)
        self.engine = MuseTalkRealtimeEngine()
        self.engine.prepare_avatar(video_path=self.avatar_video_path, bbox_shift=self.bbox_shift)

        # Create enhanced CORS middleware
        cors_middleware = create_simple_cors_middleware()
        
        self.web_app = web.Application()
        self.web_app.middlewares.append(cors_middleware)
        self.web_app.add_routes([
            web.post("/offer", self.offer),
            web.post("/upload_answer", self.upload_answer),
            web.get("/health", self.health),
            web.get("/test", self.test_page),
            web.get("/upload_sample", self.upload_sample),
        ])
        # Background tasks
        self.web_app.on_startup.append(self._start_background_tasks)
        self.web_app.on_cleanup.append(self._cleanup_background_tasks)

        self.pcs: List[RTCPeerConnection] = []

    async def _push_frames(self, frame_queue: "asyncio.Queue[VideoFrame]"):
        # Use audio path from realtime.yaml if available; otherwise fallback to latest uploaded
        source_path: Optional[str] = self.config_audio_path
        if source_path and not pathlib.Path(source_path).exists():
            # Wait for watcher/upload to create or update it
            await self.answer_event.wait()
        if not source_path or not pathlib.Path(source_path).exists():
            # Fallback to latest detected
            if self.latest_answer_path is None or not pathlib.Path(self.latest_answer_path).exists():
                await self.answer_event.wait()
            source_path = self.latest_answer_path

        print(f"[MuseTalk] WebRTC stream starting with audio: {source_path}")
        # Stream frames using a process_frames-style pipeline: generate -> process -> stream
        composed_queue: queue.Queue = queue.Queue(maxsize=4)

        def producer_recon():
            try:
                # Prepare audio features and chunks
                whisper_input_features, librosa_length = self.engine.audio_processor.get_audio_feature(
                    source_path, weight_dtype=self.engine.weight_dtype
                )
                whisper_chunks = self.engine.audio_processor.get_whisper_chunk(
                    whisper_input_features,
                    self.engine.device,
                    self.engine.weight_dtype,
                    self.engine.whisper,
                    librosa_length,
                    fps=self.fps,
                    audio_padding_length_left=2,
                    audio_padding_length_right=2,
                )
                video_num = len(whisper_chunks)

                # generation loop
                gen = datagen(
                    whisper_chunks,
                    self.engine.input_latent_list_cycle if hasattr(self.engine, 'input_latent_list_cycle') else [],
                    batch_size=20,
                )
                idx = 0
                for _, (whisper_batch, latent_batch) in enumerate(gen, start=1):
                    audio_feature_batch = self.engine.pe(whisper_batch.to(self.engine.device))
                    latent_batch = latent_batch.to(device=self.engine.device, dtype=self.engine.unet.model.dtype)
                    pred_latents = self.engine.unet.model(
                        latent_batch, self.engine.timesteps, encoder_hidden_states=audio_feature_batch
                    ).sample
                    pred_latents = pred_latents.to(device=self.engine.device, dtype=self.engine.vae.vae.dtype)
                    recon = self.engine.vae.decode_latents(pred_latents)
                    for res_frame in recon:
                        # process one frame into composed image and enqueue
                        bbox = self.engine.coord_list_cycle[idx % len(self.engine.coord_list_cycle)]
                        ori_frame = np.copy(self.engine.frame_list_cycle[idx % len(self.engine.frame_list_cycle)])
                        x1, y1, x2, y2 = bbox
                        try:
                            res_frame = cv2.resize(res_frame.astype(np.uint8), (x2 - x1, y2 - y1))
                        except Exception:
                            idx += 1
                            continue
                        mask = self.engine.mask_list_cycle[idx % len(self.engine.mask_list_cycle)]
                        mask_crop_box = self.engine.mask_coords_list_cycle[idx % len(self.engine.mask_coords_list_cycle)]
                        combined = get_image_blending(ori_frame, res_frame, bbox, mask, mask_crop_box)
                        composed_queue.put(combined)
                        idx += 1
                composed_queue.put(None)
            except Exception as e:
                print(f"[MuseTalk] Producer error: {e}")
                try:
                    composed_queue.put(None)
                except Exception:
                    pass

        prod_thread = threading.Thread(target=producer_recon, daemon=True)
        prod_thread.start()

        # consume composed images and push to WebRTC
        while True:
            composed = await asyncio.get_event_loop().run_in_executor(None, composed_queue.get)
            if composed is None:
                break
            frame_rgb = cv2.cvtColor(composed, cv2.COLOR_BGR2RGB)
            video_frame = VideoFrame.from_ndarray(frame_rgb, format="rgb24")
            await frame_queue.put(video_frame)
        prod_thread.join()
        print("[MuseTalk] WebRTC stream finished")

        # End of stream: optional trailing black frames (skip if dimensions unknown)

    async def offer(self, request: web.Request) -> web.Response:
        params = await request.json()
        offer = RTCSessionDescription(sdp=params["sdp"], type=params["type"])

        pc = RTCPeerConnection()
        self.pcs.append(pc)

        # Optional sink for incoming tracks (we do not expect any for this server)
        recorder = MediaBlackhole()

        @pc.on("track")
        async def on_track(track):
            await recorder.start()

        # Outgoing video track
        frame_queue: asyncio.Queue = asyncio.Queue(maxsize=2)
        video_track = MuseTalkVideoTrack(frame_queue, fps=self.fps)
        pc.addTrack(video_track)

        # Kick an inference session immediately if we already have an answer
        if (self.config_audio_path and os.path.exists(self.config_audio_path)) or (
            self.latest_answer_path and os.path.exists(self.latest_answer_path)
        ):
            print("[MuseTalk] Answer available at offer time; starting stream")
            asyncio.create_task(self._push_frames(frame_queue))
        else:
            print("[MuseTalk] No answer yet; waiting for watcher signal to start stream")
            async def starter():
                await self.answer_event.wait()
                await self._push_frames(frame_queue)
            asyncio.create_task(starter())

        await pc.setRemoteDescription(offer)
        answer = await pc.createAnswer()
        await pc.setLocalDescription(answer)

        return web.Response(
            content_type="application/json",
            text=json.dumps({"sdp": pc.localDescription.sdp, "type": pc.localDescription.type}),
        )

    async def upload_answer(self, request: web.Request) -> web.Response:
        try:
            reader = await request.multipart()
            field = await reader.next()
            
            if field is None or field.name != "file":
                # Support raw body as wav
                raw = await request.read()
                if not raw:
                    return web.json_response({"ok": False, "error": "no file"}, status=400)
                
                # Use improved file handler
                file_path = self.file_handler.save_audio_file(raw)
                filename = file_path.name
            else:
                # Handle multipart file upload
                filename = field.filename or f"Answer_{int(time.time()*1000)}.wav"
                raw = b""
                while True:
                    chunk = await field.read_chunk()
                    if not chunk:
                        break
                    raw += chunk
                
                # Use improved file handler
                file_path = self.file_handler.save_audio_file(raw, filename)
            
            self.latest_answer_path = str(file_path)
            self.answer_event.set()
            print(f"[MuseTalk] Uploaded answer received: {file_path}")
            # Do not clear the event; allow multiple consumers until a new upload overwrites latest path
            return web.json_response({"ok": True, "path": file_path.name})
            
        except PermissionError as e:
            print(f"[MuseTalk] Permission error uploading file: {e}")
            return web.json_response({"ok": False, "error": "permission denied"}, status=500)
        except Exception as e:
            print(f"[MuseTalk] Error uploading file: {e}")
            return web.json_response({"ok": False, "error": str(e)}, status=500)

    async def health(self, request: web.Request) -> web.Response:
        return web.json_response({
            "status": "ok",
            "have_answer": bool(self.latest_answer_path and pathlib.Path(self.latest_answer_path).exists()),
            "answers_dir": str(self.file_handler.answers_dir),
            "permissions_ok": self.file_handler.check_permissions(),
        })

    async def test_page(self, request: web.Request) -> web.Response:
        html = """
<!DOCTYPE html>
<html>
<head>
  <meta charset=\"utf-8\"/>
  <title>MuseTalk WebRTC Test</title>
  <style>
    body { font-family: Arial, sans-serif; margin: 24px; }
    button { padding: 10px 16px; }
    video { width: 640px; max-width: 100%; background: #000; display: block; margin-top: 16px; }
    #status { margin-top: 10px; padding: 8px; border-radius: 6px; background: #f1f5f9; }
  </style>
  <script>
  async function start() {
    const statusEl = document.getElementById('status');
    try {
      statusEl.textContent = 'Uploading sample audio...';
      await fetch('/upload_sample');
      statusEl.textContent = 'Creating WebRTC offer...';
      const pc = new RTCPeerConnection();
      const video = document.getElementById('v');
      pc.ontrack = (e) => { video.srcObject = e.streams[0]; };
      const offer = await pc.createOffer({ offerToReceiveVideo: true, offerToReceiveAudio: false });
      await pc.setLocalDescription(offer);
      statusEl.textContent = 'Sending offer...';
      const resp = await fetch('/offer', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ sdp: offer.sdp, type: offer.type }) });
      if (!resp.ok) throw new Error('Offer failed');
      const ans = await resp.json();
      statusEl.textContent = 'Applying answer...';
      await pc.setRemoteDescription({ type: ans.type || 'answer', sdp: ans.sdp });
      statusEl.textContent = 'Streaming...';
    } catch (e) {
      statusEl.textContent = 'Error: ' + e.message;
    }
  }
  </script>
</head>
<body>
  <h1>MuseTalk WebRTC Test</h1>
  <button onclick=\"start()\">Start Inference & Stream</button>
  <div id=\"status\"></div>
  <video id=\"v\" autoplay playsinline></video>
</body>
</html>
"""
        return web.Response(content_type="text/html", text=html)

    async def upload_sample(self, request: web.Request) -> web.Response:
        try:
            sample = os.path.join(os.path.dirname(__file__), "data", "audio", "RealTimeAudioTest.wav")
            if not os.path.exists(sample):
                return web.json_response({"ok": False, "error": "sample audio not found"}, status=404)
            
            # Read sample file
            with open(sample, "rb") as src:
                audio_data = src.read()
            
            # Use improved file handler
            file_path = self.file_handler.save_audio_file(audio_data, f"Answer_sample_{int(time.time()*1000)}.wav")
            
            self.latest_answer_path = str(file_path)
            self.answer_event.set()
            print(f"[MuseTalk] Sample answer staged: {file_path}")
            return web.json_response({"ok": True, "path": file_path.name})
        except PermissionError as e:
            print(f"[MuseTalk] Permission error uploading sample: {e}")
            return web.json_response({"ok": False, "error": "permission denied"}, status=500)
        except Exception as e:
            print(f"[MuseTalk] Error uploading sample: {e}")
            return web.json_response({"ok": False, "error": str(e)}, status=500)

    async def _start_background_tasks(self, app: web.Application):
        # Capture running loop and start improved file watcher
        self._loop = asyncio.get_running_loop()
        
        # Initialize file watcher with callback
        def on_new_audio_file(file_path: pathlib.Path):
            """Callback when new audio file is detected."""
            self.latest_answer_path = str(file_path)
            if self._loop is not None:
                self._loop.call_soon_threadsafe(self.answer_event.set)
            print(f"[MuseTalk] Detected new answer file: {file_path}")
            # Begin modified internal inference immediately (logs show progress)
            try:
                self._begin_modified_inference(str(file_path))
            except Exception as e:
                print(f"[MuseTalk] Failed to start internal inference: {e}")
        
        self._file_watcher = FileWatcher(self.file_handler.answers_dir, on_new_audio_file)
        self._file_watcher.start()
        print(f"[MuseTalk] File watcher started on {self.file_handler.answers_dir}")

    async def _cleanup_background_tasks(self, app: web.Application):
        if self._file_watcher is not None:
            self._file_watcher.stop()
            print("[MuseTalk] File watcher stopped")



    def _start_realtime_inference(self):
        """Launch the standard realtime_inference.py with skip_save_images and realtime.yaml."""
        # Build command
        cfg_rel = os.path.join("configs", "inference", "realtime.yaml")
        cmd = [sys.executable, "-m", "scripts.realtime_inference", "--inference_config", cfg_rel, "--skip_save_images"]
        # Stop previous run if still active
        if self._rt_proc and (self._rt_proc.poll() is None):
            print("[MuseTalk] Terminating previous realtime_inference process...")
            try:
                self._rt_proc.terminate()
            except Exception:
                pass
        print(f"[MuseTalk] Starting realtime_inference: {' '.join(cmd)}")
        self._rt_proc = subprocess.Popen(cmd, cwd=self._base_dir)

    def _begin_modified_inference(self, audio_path: str):
        """Start our internal streaming inference in a background thread (no streaming binding)."""
        if self._warm_infer_thread and self._warm_infer_thread.is_alive():
            # Let previous warm run finish; avoid overlapping heavy jobs
            print("[MuseTalk] Previous internal inference still running; skipping warm start")
            return

        def run():
            try:
                batch_size = 20
                fps = self.fps
                
                # Verify file exists before processing
                audio_file_path = pathlib.Path(audio_path)
                if not audio_file_path.exists():
                    print(f"[MuseTalk] [Warm] Audio file not found: {audio_path}")
                    return
                    
                print(f"[MuseTalk] [Warm] Preparing audio features for {audio_path}")
                whisper_input_features, librosa_length = self.engine.audio_processor.get_audio_feature(
                    audio_path, weight_dtype=self.engine.weight_dtype
                )
                whisper_chunks = self.engine.audio_processor.get_whisper_chunk(
                    whisper_input_features,
                    self.engine.device,
                    self.engine.weight_dtype,
                    self.engine.whisper,
                    librosa_length,
                    fps=fps,
                    audio_padding_length_left=2,
                    audio_padding_length_right=2,
                )
                video_num = len(whisper_chunks)
                total_batches = int((video_num + batch_size - 1) // batch_size)
                print(f"[MuseTalk] [Warm] Inference config: fps={fps}, batch_size={batch_size}, total_frames={video_num}, total_batches={total_batches}")

                # Producer loop with progress reporting
                gen = datagen(
                    whisper_chunks,
                    self.engine.input_latent_list_cycle if hasattr(self.engine, 'input_latent_list_cycle') else [],
                    batch_size=batch_size,
                )

                # Ensure prepared materials are present
                if not self.engine.input_latent_list_cycle:
                    # Should not happen; engine.prepare_avatar must be called
                    print("[MuseTalk] [Warm][Warn] No prepared latents; avatar may not be initialized")

                frames_done = 0
                t0 = time.time()
                for batch_index, (whisper_batch, latent_batch) in enumerate(gen, start=1):
                    bstart = time.time()
                    audio_feature_batch = self.engine.pe(whisper_batch.to(self.engine.device))
                    latent_batch = latent_batch.to(device=self.engine.device, dtype=self.engine.unet.model.dtype)
                    pred_latents = self.engine.unet.model(
                        latent_batch, self.engine.timesteps, encoder_hidden_states=audio_feature_batch
                    ).sample
                    pred_latents = pred_latents.to(device=self.engine.device, dtype=self.engine.vae.vae.dtype)
                    recon = self.engine.vae.decode_latents(pred_latents)
                    frames_done += recon.shape[0]
                    belapsed = time.time() - bstart
                    elapsed = time.time() - t0
                    eta = (elapsed / batch_index) * total_batches - elapsed if batch_index > 0 else 0
                    print(
                        f"[MuseTalk] [Warm] Batch {batch_index}/{total_batches} | frames {frames_done}/{video_num} | "
                        f"batch_time={belapsed:.2f}s | elapsed={elapsed:.2f}s | eta={eta:.2f}s"
                    )
                total_elapsed = time.time() - t0
                print(f"[MuseTalk] [Warm] Inference completed. Total frames: {frames_done}, total_time={total_elapsed:.2f}s")
            except Exception as e:
                print(f"[MuseTalk] [Warm] Inference error: {e}")

        self._warm_infer_thread = threading.Thread(target=run, daemon=True)
        self._warm_infer_thread.start()

    def run(self, host: str = "0.0.0.0", port: int = 8089):
        web.run_app(self.web_app, host=host, port=port)


def _default_avatar_from_config() -> Tuple[str, int, Optional[str]]:
    """Read `configs/inference/realtime.yaml` to get a default avatar, bbox_shift, and first audio path if available."""
    cfg_path = os.path.join(os.path.dirname(__file__), "configs", "inference", "realtime.yaml")
    if not os.path.exists(cfg_path):
        # Fallback to demo video
        return os.path.join(os.path.dirname(__file__), "data", "video", "1FrameVideo.mp4"), 0, None
    cfg = OmegaConf.load(cfg_path)
    # Take first entry
    first_key = next(iter(cfg))
    entry = cfg[first_key]
    video_path = entry.get("video_path", os.path.join(os.path.dirname(__file__), "data", "video", "1FrameVideo.mp4"))
    bbox_shift = int(entry.get("bbox_shift", 0))
    audio_path = None
    clips = entry.get("audio_clips", {})
    if isinstance(clips, dict) and len(clips) > 0:
        # first value
        audio_path = next(iter(clips.values()))
        # Normalize to absolute path relative to this file if needed
        if not os.path.isabs(audio_path):
            audio_path = os.path.normpath(os.path.join(os.path.dirname(__file__), audio_path))
    return video_path, bbox_shift, audio_path

def _load_realtime_config_defaults(avatar_override: Optional[str], bbox_override: Optional[int]) -> Tuple[str, int, Optional[str]]:
    """Helper used by server to pull defaults from realtime.yaml with optional overrides."""
    video_path, bbox_shift, audio_path = _default_avatar_from_config()
    if avatar_override:
        video_path = avatar_override
    if bbox_override is not None:
        bbox_shift = bbox_override
    return video_path, bbox_shift, audio_path


if __name__ == "__main__":
    avatar_path, bbox_shift, _ = _default_avatar_from_config()
    server = MuseTalkWebRTCServer(
        avatar_video_path=avatar_path,
        bbox_shift=bbox_shift,
        fps=25,
    )
    server.run(host="0.0.0.0", port=8090)


