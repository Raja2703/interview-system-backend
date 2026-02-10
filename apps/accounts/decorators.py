# apps/accounts/decorators.py
"""
Custom decorators for authentication rate limiting and security.
"""

import logging
from functools import wraps
from django.http import JsonResponse
from django.core.cache import cache

logger = logging.getLogger(__name__)

def rate_limit(key_prefix, limit=5, period=60):
    """
    Rate limiting decorator for authentication endpoints.
    
    Args:
        key_prefix: Prefix for the cache key
        limit: Maximum number of requests allowed
        period: Time period in seconds
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            # Get client IP
            x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
            if x_forwarded_for:
                ip = x_forwarded_for.split(',')[0].strip()
            else:
                ip = request.META.get('REMOTE_ADDR', 'unknown')
            
            cache_key = f"{key_prefix}:{ip}"
            
            # Get current count
            current_count = cache.get(cache_key, 0)
            
            if current_count >= limit:
                logger.warning(f"Rate limit exceeded for {ip} on {key_prefix}")
                return JsonResponse({
                    "error": "Too many requests. Please try again later.",
                    "retry_after": period
                }, status=429)
            
            # Increment count
            cache.set(cache_key, current_count + 1, period)
            
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator


def log_auth_attempt(view_func):
    """
    Decorator to log authentication attempts.
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        # Get client info
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0].strip()
        else:
            ip = request.META.get('REMOTE_ADDR', 'unknown')
        
        user_agent = request.META.get('HTTP_USER_AGENT', 'unknown')
        
        logger.info(f"Auth attempt from IP: {ip}, User-Agent: {user_agent[:100]}")
        
        response = view_func(request, *args, **kwargs)
        
        # Log result
        if hasattr(response, 'status_code'):
            if response.status_code == 200:
                logger.info(f"Auth success from IP: {ip}")
            else:
                logger.warning(f"Auth failed from IP: {ip}, Status: {response.status_code}")
        
        return response
    return wrapper