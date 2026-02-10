# apps/common/utils.py
from django.http import JsonResponse
from django.conf import settings
from rest_framework.views import exception_handler
from rest_framework.response import Response
from rest_framework import status as http_status
import logging

logger = logging.getLogger(__name__)


def custom_exception_handler(exc, context):
    """
    Custom exception handler for Django REST Framework.
    
    This ensures ALL exceptions return JSON responses instead of HTML error pages.
    
    Args:
        exc: The exception raised
        context: Context dict with 'view' and 'request'
    
    Returns:
        Response: JSON response with error details
    """
    # Call REST framework's default handler first to get the standard error response
    response = exception_handler(exc, context)
    
    if response is not None:
        # DRF successfully handled the exception (400, 401, 403, 404, etc.)
        # Standardize the error format
        custom_response_data = {
            'error': True,
            'status_code': response.status_code,
        }
        
        # Extract error message
        if isinstance(response.data, dict):
            # If there's a 'detail' key, use it as the main message
            if 'detail' in response.data:
                custom_response_data['message'] = str(response.data['detail'])
                # Include other fields as details if present
                if len(response.data) > 1:
                    custom_response_data['details'] = {
                        k: v for k, v in response.data.items() if k != 'detail'
                    }
            else:
                # Use all data as details
                custom_response_data['message'] = 'Validation error' if response.status_code == 400 else 'Request failed'
                custom_response_data['details'] = response.data
        elif isinstance(response.data, list):
            custom_response_data['message'] = 'Multiple errors occurred'
            custom_response_data['details'] = response.data
        else:
            custom_response_data['message'] = str(response.data)
        
        response.data = custom_response_data
        return response
    
    # Handle unhandled exceptions (500 errors)
    # These are exceptions that DRF didn't catch
    logger.exception(f"Unhandled exception in {context.get('view', 'unknown view')}: {exc}")
    
    # Build error response
    error_response = {
        'error': True,
        'status_code': 500,
        'message': 'An internal server error occurred.',
    }
    
    # Include exception details only in DEBUG mode
    if settings.DEBUG:
        error_response['debug'] = {
            'exception_type': exc.__class__.__name__,
            'exception_message': str(exc),
            'view': str(context.get('view', 'Unknown')),
        }
    else:
        error_response['message'] = 'An internal server error occurred. Please contact support.'
    
    return Response(error_response, status=http_status.HTTP_500_INTERNAL_SERVER_ERROR)


def custom_404(request, exception=None):
    """
    Custom 404 error handler that returns JSON.
    """
    return JsonResponse({
        'error': 'Not Found',
        'message': 'The requested resource was not found.'
    }, status=404)


def custom_500(request):
    """
    Custom 500 error handler that returns JSON.
    """
    return JsonResponse({
        'error': 'Internal Server Error',
        'message': 'An unexpected error occurred on the server.'
    }, status=500)
