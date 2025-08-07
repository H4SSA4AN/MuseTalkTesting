"""
Web interface server for MuseTalk
"""

import sys
import os
from aiohttp import web
import aiohttp
from config import WEB_SERVER_CONFIG, CLIENT_CONFIG

routes = web.RouteTableDef()


@routes.get("/")
async def index(request):
    """Serve the main HTML page"""
    try:
        with open("webrtc/templates/index.html", "r") as f:
            html_content = f.read()
        return web.Response(text=html_content, content_type="text/html")
    except FileNotFoundError:
        return web.Response(text="Template file not found", status=404)


@routes.get("/get_settings")
async def get_settings(request):
    """Proxy get settings request to MuseTalk server"""
    musetalk_url = f"{CLIENT_CONFIG['musetalk_server_url']}/get_settings"
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(musetalk_url) as response:
                result = await response.json()
                return web.json_response(result)
    except Exception as e:
        return web.json_response({"success": False, "error": f"Failed to connect to MuseTalk server: {str(e)}"})


@routes.post("/update_settings")
async def update_settings(request):
    """Proxy update settings request to MuseTalk server"""
    musetalk_url = f"{CLIENT_CONFIG['musetalk_server_url']}/update_settings"
    
    try:
        # Get the JSON data from the request
        data = await request.json()
        
        async with aiohttp.ClientSession() as session:
            async with session.post(musetalk_url, json=data) as response:
                result = await response.json()
                return web.json_response(result)
    except Exception as e:
        return web.json_response({"success": False, "error": f"Failed to connect to MuseTalk server: {str(e)}"})


@routes.get("/start")
async def start_inference(request):
    """Proxy start request to MuseTalk server"""
    musetalk_url = f"{CLIENT_CONFIG['musetalk_server_url']}/start"
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(musetalk_url) as response:
                result = await response.json()
                return web.json_response(result)
    except Exception as e:
        return web.json_response({"success": False, "error": f"Failed to connect to MuseTalk server: {str(e)}"})


@routes.get("/reset")
async def reset_inference(request):
    """Proxy reset request to MuseTalk server"""
    musetalk_url = f"{CLIENT_CONFIG['musetalk_server_url']}/reset"
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(musetalk_url) as response:
                result = await response.json()
                return web.json_response(result)
    except Exception as e:
        return web.json_response({"success": False, "error": f"Failed to connect to MuseTalk server: {str(e)}"})


@routes.get("/status")
async def get_status(request):
    """Proxy status request to MuseTalk server"""
    musetalk_url = f"{CLIENT_CONFIG['musetalk_server_url']}/status"
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(musetalk_url) as response:
                result = await response.json()
                return web.json_response(result)
    except Exception as e:
        return web.json_response({"success": False, "error": f"Failed to connect to MuseTalk server: {str(e)}"})


@routes.get("/audio")
async def serve_audio(request):
    """Proxy audio request to MuseTalk server"""
    musetalk_url = f"{CLIENT_CONFIG['musetalk_server_url']}/audio"
    
    print(f"Audio request received, proxying to: {musetalk_url}")
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(musetalk_url) as response:
                if response.status == 200:
                    audio_data = await response.read()
                    print(f"Audio proxy successful: {len(audio_data)} bytes")
                    return web.Response(body=audio_data, headers={
                        'Content-Type': 'audio/wav',
                        'Content-Length': str(len(audio_data)),
                        'Cache-Control': 'no-cache'  # Prevent caching
                    })
                else:
                    print(f"Audio proxy failed: {response.status}")
                    return web.Response(text="Audio file not found", status=404)
    except Exception as e:
        print(f"Audio proxy error: {e}")
        return web.Response(text=f"Failed to connect to MuseTalk server: {str(e)}", status=500)


@routes.get("/stream_status")
async def stream_status(request):
    """Proxy stream status request to MuseTalk server"""
    musetalk_url = f"{CLIENT_CONFIG['musetalk_server_url']}/stream_status"
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(musetalk_url) as response:
                result = await response.json()
                return web.json_response(result)
    except Exception as e:
        return web.json_response({"stream_ready": False, "inference_complete": False, "error": str(e)})


@routes.get("/stream")
async def stream(request):
    """Proxy stream request to MuseTalk server"""
    musetalk_url = f"{CLIENT_CONFIG['musetalk_server_url']}/stream"
    
    async def stream_response():
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(musetalk_url) as response:
                    if response.status == 200:
                        print("Proxying stream from MuseTalk server...")
                        async for chunk in response.content.iter_chunked(8192):
                            yield chunk
                    else:
                        error_msg = f"Stream not available: {response.status}"
                        print(error_msg)
                        yield error_msg.encode()
        except Exception as e:
            error_msg = f"Failed to connect to MuseTalk server: {str(e)}"
            print(error_msg)
            yield error_msg.encode()
    
    return web.Response(
        body=stream_response(),
        status=200,
        headers={"Content-Type": "multipart/x-mixed-replace; boundary=frame"}
    )


def main():
    """Main server entry point"""
    # Create and configure the web application
    app = web.Application()
    app.add_routes(routes)
    
    # Start the server
    print(f"Web interface server starting...")
    print(f"Server will be available at: http://{WEB_SERVER_CONFIG['host']}:{WEB_SERVER_CONFIG['port']}")
    print(f"Connecting to MuseTalk server at: {CLIENT_CONFIG['musetalk_server_url']}")
    
    web.run_app(app, host=WEB_SERVER_CONFIG["host"], port=WEB_SERVER_CONFIG["port"])


if __name__ == "__main__":
    main()