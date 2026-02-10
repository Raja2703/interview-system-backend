# config/asgi.py
"""
ASGI config for interview_platform project.

Configures both HTTP and WebSocket protocol handling.
WebSocket connections are authenticated via JWT token.
"""
import os
from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

# Initialize Django ASGI application early to ensure app registry is ready
django_asgi_app = get_asgi_application()

# Import after Django setup
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.security.websocket import AllowedHostsOriginValidator
from apps.notifications.middleware import JWTAuthMiddlewareStack
import apps.notifications.routing


application = ProtocolTypeRouter(
    {
        "http": django_asgi_app,
        "websocket": JWTAuthMiddlewareStack(
            URLRouter(apps.notifications.routing.websocket_urlpatterns)
        ),
    }
)
