#apps\accounts\middleware_debug.py
import logging
import traceback

logger = logging.getLogger(__name__)

class AllauthDebugMiddleware:
    """Middleware to catch and log allauth exceptions"""
    
    def __init__(self, get_response):
        self.get_response = get_response
    
    def __call__(self, request):
        return self.get_response(request)
    
    def process_exception(self, request, exception):
        if 'linkedin' in request.path.lower():
            logger.error(f"Exception in LinkedIn OAuth flow: {exception}")
            logger.error(f"Exception type: {type(exception).__name__}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            logger.error(f"Request path: {request.path}")
            logger.error(f"Request GET params: {dict(request.GET)}")
        return None