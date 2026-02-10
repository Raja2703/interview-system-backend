# apps/notifications/middleware.py
"""
WebSocket Authentication Middleware for Django Channels.

Provides JWT token authentication for WebSocket connections.
Token can be passed via:
1. Query parameter: ws://host/ws/notifications/?token=<jwt_token>
2. Header in initial handshake (if supported by client)
"""
import logging
from urllib.parse import parse_qs
from django.contrib.auth.models import AnonymousUser
from channels.db import database_sync_to_async
from channels.middleware import BaseMiddleware
from channels.auth import AuthMiddlewareStack
from rest_framework_simplejwt.tokens import AccessToken
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from django.contrib.auth import get_user_model

logger = logging.getLogger(__name__)
User = get_user_model()


class JWTAuthMiddleware(BaseMiddleware):
    """
    JWT Authentication middleware for Django Channels WebSocket.
    
    Authenticates WebSocket connections using JWT token passed as a query parameter.
    
    Usage:
        Connect to: ws://host/ws/notifications/?token=<jwt_access_token>
    
    The middleware validates the token and attaches the user to the scope.
    If authentication fails, AnonymousUser is attached.
    """
    
    async def __call__(self, scope, receive, send):
        # Get query string from scope
        query_string = scope.get('query_string', b'').decode('utf-8')
        query_params = parse_qs(query_string)
        
        # Extract token from query parameters
        token = None
        if 'token' in query_params:
            token = query_params['token'][0]
        
        # Authenticate user
        scope['user'] = await self._get_user_from_token(token)
        
        return await super().__call__(scope, receive, send)
    
    @database_sync_to_async
    def _get_user_from_token(self, token):
        """
        Validate JWT token and return the associated user.
        
        Args:
            token: JWT access token string
            
        Returns:
            User instance if valid, AnonymousUser if invalid
        """
        if not token:
            logger.debug("No token provided for WebSocket connection")
            return AnonymousUser()
        
        try:
            # Validate the token
            access_token = AccessToken(token)
            
            # Get user ID from token
            user_id = access_token.get('user_id')
            
            if not user_id:
                logger.warning("No user_id in token")
                return AnonymousUser()
            
            # Get user from database
            try:
                user = User.objects.select_related('profile').get(id=user_id)
                logger.debug(f"WebSocket authenticated user: {user.email}")
                return user
            except User.DoesNotExist:
                logger.warning(f"User not found for token user_id: {user_id}")
                return AnonymousUser()
                
        except (InvalidToken, TokenError) as e:
            logger.warning(f"Invalid WebSocket token: {str(e)}")
            return AnonymousUser()
        except Exception as e:
            logger.error(f"WebSocket auth error: {str(e)}")
            return AnonymousUser()


def JWTAuthMiddlewareStack(inner):
    """
    Utility function to wrap ASGI application with JWT authentication.
    
    Combines AuthMiddlewareStack (for session auth) with JWTAuthMiddleware.
    This allows both session-based and JWT-based authentication.
    
    Usage in asgi.py:
        from apps.notifications.middleware import JWTAuthMiddlewareStack
        
        application = ProtocolTypeRouter({
            "websocket": JWTAuthMiddlewareStack(
                URLRouter(websocket_urlpatterns)
            ),
        })
    """
    return JWTAuthMiddleware(AuthMiddlewareStack(inner))
