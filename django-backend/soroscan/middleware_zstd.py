import asyncio
import zstandard as zstd
from django.utils.decorators import sync_and_async_middleware

@sync_and_async_middleware
def ZstdMiddleware(get_response):
    """
    Middleware to compress responses using zstd if the client supports it
    and the response is larger than 1KB.
    """
    
    # One-time configuration and initialization.

    if asyncio.iscoroutinefunction(get_response):
        async def middleware(request):
            response = await get_response(request)
            return _apply_zstd(request, response)
    else:
        def middleware(request):
            response = get_response(request)
            return _apply_zstd(request, response)

    return middleware


def _apply_zstd(request, response):
    """Apply zstd compression to a response if appropriate."""
    # Check if client accepts zstd
    accept_encoding = request.META.get('HTTP_ACCEPT_ENCODING', '')
    if 'zstd' not in accept_encoding:
        return response
        
    # Check if it's already compressed or streaming
    if response.has_header('Content-Encoding') or getattr(response, 'streaming', False):
        return response
        
    # Check if response is large enough
    if len(response.content) < 1024:
        return response
        
    # Compress
    cctx = zstd.ZstdCompressor()
    compressed_content = cctx.compress(response.content)
    
    # Update response
    response.content = compressed_content
    response['Content-Encoding'] = 'zstd'
    response['Content-Length'] = str(len(response.content))
    
    # Add Vary header
    vary = response.get('Vary', None)
    if vary:
        if 'accept-encoding' not in vary.lower():
            response['Vary'] = vary + ', Accept-Encoding'
    else:
        response['Vary'] = 'Accept-Encoding'
        
    return response

