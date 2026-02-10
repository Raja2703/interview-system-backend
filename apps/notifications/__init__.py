# apps/notifications/__init__.py
"""
Notification system for Interview Platform.

Provides:
- Notification model for storing notifications
- REST APIs for notification CRUD
- WebSocket delivery via Django Channels
"""
default_app_config = 'apps.notifications.apps.NotificationsConfig'
