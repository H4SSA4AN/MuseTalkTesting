"""
Enhanced CORS middleware for MuseTalk server
"""

import re
from aiohttp import web


def create_cors_middleware(allowed_origins=None):
    """
    Create enhanced CORS middleware
    
    Args:
        allowed_origins: List of allowed origins, or None for all origins
    """
    
    if allowed_origins is None:
        # Allow all origins for development
        allowed_origins = ["*"]
    
    def is_origin_allowed(origin):
        """Check if origin is allowed"""
        if "*" in allowed_origins:
            return True
        return origin in allowed_origins
    
    async def cors_middleware(app, handler):
        async def middleware(request):
            # Get the origin from the request
            origin = request.headers.get('Origin', '')
            
            # Handle preflight OPTIONS requests
            if request.method == 'OPTIONS':
                headers = {
                    "Access-Control-Allow-Origin": origin if is_origin_allowed(origin) else "",
                    "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS",
                    "Access-Control-Allow-Headers": "Content-Type, Authorization, X-Requested-With, Accept, Origin",
                    "Access-Control-Max-Age": "86400",
                }
                return web.Response(status=200, headers=headers)
            
            # Handle actual requests
            try:
                response = await handler(request)
            except web.HTTPException as e:
                response = e
            
            # Add CORS headers to all responses
            if is_origin_allowed(origin):
                response.headers["Access-Control-Allow-Origin"] = origin
            else:
                response.headers["Access-Control-Allow-Origin"] = ""
            
            response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
            response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, X-Requested-With, Accept, Origin"
            response.headers["Access-Control-Expose-Headers"] = "Content-Length, Content-Range"
            
            return response
        
        return middleware
    
    return cors_middleware


def create_simple_cors_middleware():
    """
    Create a simple CORS middleware that allows all origins
    This is the most permissive version for development
    """
    
    async def cors_middleware(app, handler):
        async def middleware(request):
            # Handle preflight requests
            if request.method == 'OPTIONS':
                return web.Response(
                    status=200,
                    headers={
                        "Access-Control-Allow-Origin": "*",
                        "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS, HEAD",
                        "Access-Control-Allow-Headers": "*",
                        "Access-Control-Max-Age": "86400",
                        "Access-Control-Expose-Headers": "*"
                    }
                )
            
            # Handle actual requests
            try:
                response = await handler(request)
            except web.HTTPException as e:
                response = e
            
            # Add CORS headers to all responses
            response.headers["Access-Control-Allow-Origin"] = "*"
            response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS, HEAD"
            response.headers["Access-Control-Allow-Headers"] = "*"
            response.headers["Access-Control-Expose-Headers"] = "*"
            
            return response
        
        return middleware
    
    return cors_middleware


def create_network_cors_middleware():
    """
    Create CORS middleware that allows local network origins
    This is useful for cross-device communication on the same network
    """
    
    # Common local network patterns
    local_network_patterns = [
        r'^http://localhost:\d+$',
        r'^http://127\.0\.0\.1:\d+$',
        r'^http://192\.168\.\d+\.\d+:\d+$',
        r'^http://10\.\d+\.\d+\.\d+:\d+$',
        r'^http://172\.(1[6-9]|2[0-9]|3[0-1])\.\d+\.\d+:\d+$',
        r'^https://localhost:\d+$',
        r'^https://127\.0\.0\.1:\d+$',
        r'^https://192\.168\.\d+\.\d+:\d+$',
        r'^https://10\.\d+\.\d+\.\d+:\d+$',
        r'^https://172\.(1[6-9]|2[0-9]|3[0-1])\.\d+\.\d+:\d+$',
    ]
    
    def is_local_network_origin(origin):
        """Check if origin is from local network"""
        for pattern in local_network_patterns:
            if re.match(pattern, origin):
                return True
        return False
    
    async def cors_middleware(app, handler):
        async def middleware(request):
            origin = request.headers.get('Origin', '')
            
            # Handle preflight requests
            if request.method == 'OPTIONS':
                headers = {
                    "Access-Control-Allow-Origin": origin if is_local_network_origin(origin) else "",
                    "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS, HEAD",
                    "Access-Control-Allow-Headers": "*",
                    "Access-Control-Max-Age": "86400",
                    "Access-Control-Expose-Headers": "*"
                }
                return web.Response(status=200, headers=headers)
            
            # Handle actual requests
            try:
                response = await handler(request)
            except web.HTTPException as e:
                response = e
            
            # Add CORS headers
            if is_local_network_origin(origin):
                response.headers["Access-Control-Allow-Origin"] = origin
            else:
                response.headers["Access-Control-Allow-Origin"] = ""
            
            response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS, HEAD"
            response.headers["Access-Control-Allow-Headers"] = "*"
            response.headers["Access-Control-Expose-Headers"] = "*"
            
            return response
        
        return middleware
    
    return cors_middleware
