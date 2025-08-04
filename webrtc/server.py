# server.py

import asyncio
import json
import fractions
from aiohttp import web, WSCloseCode
import aiohttp_cors
from aiortc import RTCPeerConnection, RTCSessionDescription, VideoStreamTrack
from aiortc.contrib.media import MediaRelay
from av import VideoFrame

# Import your MuseTalk frame generator
# Replace this with the actual import path in your project
from scripts.realtime_inference import process_frames

# Globals
pcs = {}      # maps WebSocket -> RTCPeerConnection
relay = MediaRelay()

# --- Custom VideoTrack wrapping MuseTalk frames ---
class AvatarTrack(VideoStreamTrack):
    def __init__(self, frame_gen, fps=30):
        super().__init__()  # initialize base class
        self._gen = frame_gen
        self._frame_time = 1 / fps
        self._next_ts = None

    async def recv(self):
        """
        Called by aiortc when it needs the next video frame.
        """
        # initialize timestamp
        if self._next_ts is None:
            self._next_ts = asyncio.get_event_loop().time()

        # wait if we're ahead of schedule
        now = asyncio.get_event_loop().time()
        wait = self._next_ts - now
        if wait > 0:
            await asyncio.sleep(wait)

        # pull the next frame (numpy H×W×3 uint8 BGR)
        frame_nd = next(self._gen)
        # convert to an av.VideoFrame
        video_frame = VideoFrame.from_ndarray(frame_nd, format="bgr24")
        # assign timestamp (90 kHz clock)
        video_frame.pts = int(self._next_ts * 90000)
        video_frame.time_base = fractions.Fraction(1, 90000)

        # schedule next frame
        self._next_ts += self._frame_time
        return video_frame

# --- HTTP & WebSocket handlers ---
routes = web.RouteTableDef()

@routes.get("/")
async def index(request):
    return web.FileResponse("public/index.html")

@routes.get("/client.js")
async def client_js(request):
    return web.FileResponse("public/client.js")

@routes.get("/ws")
async def websocket_handler(request):
    """
    WebSocket handler for signaling.
    Supports actions: join, offer, answer, ice-candidate, start-avatar.
    """
    ws = web.WebSocketResponse()
    await ws.prepare(request)

    # create a PeerConnection for this client
    pc = RTCPeerConnection()
    pcs[ws] = pc

    # handle incoming WebSocket messages
    async for msg in ws:
        if msg.type != web.WSMsgType.TEXT:
            continue

        data = json.loads(msg.data)
        action = data.get("action")

        if action == "join":
            # client is ready for initial negotiation
            # prompt client to create an offer
            await ws.send_json({"action": "renegotiate"})

        elif action == "offer":
            # client sent an SDP offer
            offer = RTCSessionDescription(sdp=data["sdp"], type=data["type"])
            await pc.setRemoteDescription(offer)

            # create and send back an answer
            answer = await pc.createAnswer()
            await pc.setLocalDescription(answer)
            await ws.send_json({
                "action": "answer",
                "sdp":    pc.localDescription.sdp,
                "type":   pc.localDescription.type
            })

        elif action == "answer":
            # client answered our offer (only on renegotiation)
            answer = RTCSessionDescription(sdp=data["sdp"], type=data["type"])
            await pc.setRemoteDescription(answer)

        elif action == "ice-candidate":
            # ICE candidate from client
            candidate = data.get("candidate")
            if candidate:
                try:
                    await pc.addIceCandidate(candidate)
                except Exception:
                    pass

        elif action == "start-avatar":
            # client requested to start MuseTalk avatar stream
            # launch the frame generator with your preloaded inputs
            frame_gen = process_frames(
                audio="path/to/preloaded_audio.wav",
                reference_video="path/to/preloaded_ref.mp4",
                batch_size=1,
                fps=30
            )
            # wrap it in our VideoStreamTrack
            avatar_track = AvatarTrack(frame_gen, fps=30)
            pc.addTrack(avatar_track)

            # tell client to renegotiate so it sees the new video track
            await ws.send_json({"action": "renegotiate"})

        else:
            print("Unknown action:", action)

    # cleanup on socket close
    await pc.close()
    pcs.pop(ws, None)
    return ws

async def on_shutdown(app):
    # close all peer connections
    coros = [pc.close() for pc in pcs.values()]
    await asyncio.gather(*coros)
    pcs.clear()

if __name__ == "__main__":
    app = web.Application()
    app.add_routes(routes)

    # enable CORS to allow client.js if hosted separately
    cors = aiohttp_cors.setup(app)
    for route in list(app.router.routes()):
        cors.add(route)

    app.on_shutdown.append(on_shutdown)
    web.run_app(app, host="0.0.0.0", port=8080)
