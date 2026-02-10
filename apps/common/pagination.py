# apps/common/pagination.py
"""
Global Pagination Configuration for the Interview Platform API.

This module provides a reusable, production-ready pagination class
that supports limit/offset query parameters for all GET/list endpoints.

Usage:
    This pagination is applied globally via REST_FRAMEWORK settings.
    All ListAPIView and ViewSet list endpoints will automatically support:
    
    Query Parameters:
        - limit: Number of items to return (default: 10, max: 100)
        - offset: Starting position in the result set (default: 0)
    
    Example Requests:
        GET /api/interviews/?limit=20&offset=0     → First 20 items
        GET /api/interviews/?limit=20&offset=20    → Items 21-40
        GET /api/profiles/attender/?limit=50       → First 50 attender profiles
    
    Response Format (DRF Standard):
        {
            "count": 150,                → Total number of items
            "next": "...?limit=10&offset=20",   → URL for next page (or null)
            "previous": "...?limit=10&offset=0", → URL for previous page (or null)
            "results": [...]             → Paginated data array
        }
"""

from rest_framework.pagination import LimitOffsetPagination


class StandardLimitOffsetPagination(LimitOffsetPagination):
    """
    Custom LimitOffsetPagination with sensible defaults and safety limits.
    
    This pagination class provides:
    - Configurable limit via query parameter
    - Offset-based navigation for large datasets
    - Protection against excessive data retrieval via max_limit
    - DRF-standard response format (count, next, previous, results)
    
    Attributes:
        default_limit (int): Default number of items per page (10)
        max_limit (int): Maximum allowed items per request (100)
        limit_query_param (str): Query parameter name for limit ('limit')
        offset_query_param (str): Query parameter name for offset ('offset')
    
    Example:
        GET /api/interviews/?limit=25&offset=50
        → Returns items 51-75 (assuming 25 items are available after offset 50)
    """
    
    # Default number of items returned when 'limit' is not specified
    default_limit = 10
    
    # Maximum number of items that can be requested (prevents abuse/memory issues)
    max_limit = 100
    
    # Query parameter names
    limit_query_param = 'limit'
    offset_query_param = 'offset'
    
    # Template for pagination controls in browsable API (optional)
    template = 'rest_framework/pagination/numbers.html'
    
    def get_limit(self, request):
        """
        Override to ensure limit is always within bounds.
        
        Returns:
            int: The limit value, clamped between 1 and max_limit
        """
        limit = super().get_limit(request)
        
        # Ensure limit is at least 1
        if limit is not None and limit < 1:
            return self.default_limit
        
        return limit
    
    def get_schema_operation_parameters(self, view):
        """
        Return OpenAPI schema parameters for Swagger/drf-yasg documentation.
        
        This method is called by drf-yasg to generate the query parameters
        in the Swagger UI for list endpoints.
        
        Returns:
            list: List of OpenAPI parameter dictionaries
        """
        return [
            {
                'name': self.limit_query_param,
                'required': False,
                'in': 'query',
                'description': (
                    f'Number of results to return per request. '
                    f'Default: {self.default_limit}, Maximum: {self.max_limit}. '
                    f'Example: ?limit=25'
                ),
                'schema': {
                    'type': 'integer',
                    'default': self.default_limit,
                    'minimum': 1,
                    'maximum': self.max_limit,
                },
            },
            {
                'name': self.offset_query_param,
                'required': False,
                'in': 'query',
                'description': (
                    'The initial index from which to return results. '
                    'Used for pagination. Default: 0. '
                    'Example: ?limit=10&offset=20 returns items 21-30'
                ),
                'schema': {
                    'type': 'integer',
                    'default': 0,
                    'minimum': 0,
                },
            },
        ]

