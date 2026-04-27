from rest_framework.views import exception_handler

def custom_exception_handler(exc, context):
    """
    Centralized error handler for REST framework to append the request_id
    to all error payloads.
    """
    # Call REST framework's default exception handler first
    response = exception_handler(exc, context)

    # Append request_id to the error response
    if response is not None and isinstance(response.data, dict):
        request = context.get('request')
        if request and hasattr(request, 'request_id'):
            response.data["request_id"] = request.request_id

    return response
