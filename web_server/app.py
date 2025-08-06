"""
Web Server for MuseTalk - Client Side
This runs on the client machine and communicates with the inference server
"""

import asyncio
import aiohttp
from aiohttp import web
import json
import os

# Configuration
INFERENCE_SERVER_URL = "http://192.168.1.11:8080"  # Change to your inference machine IP
WEB_SERVER_HOST = "0.0.0.0"
WEB_SERVER_PORT = 3000

routes = web.RouteTableDef()

@routes.get("/")
async def index(request):
    """Serve the main HTML page"""
    try:
        with open("templates/index.html", "r") as f:
            html_content = f.read()
        return web.Response(text=html_content, content_type="text/html")
    except FileNotFoundError:
        return web.Response(text="Template file not found", status=404)

@routes.post("/start")
async def start_inference(request):
    """Proxy start request to inference server with FPS and batch size"""
    try:
        # Get FPS and batch size from request body
        body = await request.json()
        fps = body.get('fps', 25)
        batch_size = body.get('batch_size', 4)
        
        # Forward to inference server
        async with aiohttp.ClientSession() as session:
            async with session.post(f"{INFERENCE_SERVER_URL}/start", json={
                'fps': fps,
                'batch_size': batch_size
            }) as response:
                data = await response.json()
                return web.json_response(data)
    except Exception as e:
        return web.json_response({"success": False, "error": f"Connection failed: {str(e)}"})

@routes.get("/audio")
async def serve_audio(request):
    """Proxy audio request to inference server"""
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(f"{INFERENCE_SERVER_URL}/audio") as response:
                if response.status == 200:
                    audio_data = await response.read()
                    return web.Response(body=audio_data, headers={
                        'Content-Type': 'audio/wav',
                        'Content-Length': str(len(audio_data))
                    })
                else:
                    return web.Response(text="Audio not available", status=404)
        except Exception as e:
            return web.Response(text=f"Connection failed: {str(e)}", status=500)

@routes.get("/server_status")
async def server_status(request):
    """Proxy server status request to inference server"""
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(f"{INFERENCE_SERVER_URL}/server_status") as response:
                data = await response.json()
                return web.json_response(data)
        except Exception as e:
            return web.json_response({"server_ready": False, "status": "error", "error": str(e)})

@routes.get("/debug_state")
async def debug_state(request):
    """Proxy debug state request to inference server"""
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(f"{INFERENCE_SERVER_URL}/debug_state") as response:
                data = await response.json()
                return web.json_response(data)
        except Exception as e:
            return web.json_response({"error": str(e)})

@routes.get("/reset_state")
async def reset_state(request):
    """Proxy reset state request to inference server"""
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(f"{INFERENCE_SERVER_URL}/reset_state") as response:
                data = await response.json()
                return web.json_response(data)
        except Exception as e:
            return web.json_response({"success": False, "error": str(e)})

@routes.get("/test_connection")
async def test_connection(request):
    """Test connection to inference server"""
    async with aiohttp.ClientSession() as session:
        try:
            # Test basic connection
            async with session.get(f"{INFERENCE_SERVER_URL}/server_status") as response:
                if response.status == 200:
                    data = await response.json()
                    return web.json_response({
                        "connection": "success",
                        "server_status": data,
                        "inference_server_url": INFERENCE_SERVER_URL
                    })
                else:
                    return web.json_response({
                        "connection": "failed",
                        "status": response.status,
                        "inference_server_url": INFERENCE_SERVER_URL
                    })
        except Exception as e:
            return web.json_response({
                "connection": "failed",
                "error": str(e),
                "inference_server_url": INFERENCE_SERVER_URL
            })

@routes.get("/stream_status")
async def stream_status(request):
    """Proxy status request to inference server"""
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(f"{INFERENCE_SERVER_URL}/stream_status") as response:
                data = await response.json()
                return web.json_response(data)
        except Exception as e:
            return web.json_response({"stream_ready": False, "inference_complete": False, "error": str(e)})

@routes.get("/stream")
async def stream(request):
    """Proxy stream request to inference server"""
    print("Web server: Received stream request")
    async with aiohttp.ClientSession() as session:
        try:
            print("Web server: Connecting to inference server for stream")
            async with session.get(f"{INFERENCE_SERVER_URL}/stream") as response:
                if response.status == 200:
                    print("Web server: Stream response received, streaming to client")
                    
                    # Create streaming response
                    stream_response = web.StreamResponse(
                        status=200,
                        headers={"Content-Type": "multipart/x-mixed-replace; boundary=frame"}
                    )
                    
                    # Start the response
                    await stream_response.prepare(request)
                    
                    # Stream data from inference server to client
                    async for chunk in response.content.iter_chunked(8192):
                        await stream_response.write(chunk)
                    
                    await stream_response.write_eof()
                    return stream_response
                else:
                    print(f"Web server: Stream not available, status: {response.status}")
                    return web.Response(text="Stream not available", status=404)
        except Exception as e:
            print(f"Web server: Stream connection failed: {str(e)}")
            return web.Response(text=f"Connection failed: {str(e)}", status=500)

def main():
    """Main server entry point"""
    app = web.Application()
    app.add_routes(routes)
    
    print(f"Web Server starting...")
    print(f"Server will be available at: http://{WEB_SERVER_HOST}:{WEB_SERVER_PORT}")
    print(f"Connecting to inference server at: {INFERENCE_SERVER_URL}")
    
    web.run_app(app, host=WEB_SERVER_HOST, port=WEB_SERVER_PORT)

if __name__ == "__main__":
    main()