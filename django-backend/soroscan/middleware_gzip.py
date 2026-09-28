
from django.middleware.gzip import GZipMiddleware


class CustomGZipMiddleware(GZipMiddleware):
    """
    Custom Gzip middleware that only compresses responses larger than 1KB
    to save CPU cycles on very small responses.
    """
    
    def process_response(self, request, response):
        # We want to use the parent's logic, but we need to override the 200 bytes threshold.
        # Unfortunately, GZipMiddleware hardcodes the 200 bytes threshold.
        # So we basically reimplement the check here.
        
        # It's not worth compressing non-OK or non-content responses
        if response.has_header("Content-Encoding") or not response.streaming and len(response.content) < 1024:
            return response

        # Call the parent's process_response, which will compress it
        # (It will check for 200 bytes, but since we already filtered out < 1024, it works fine).
        return super().process_response(request, response)
