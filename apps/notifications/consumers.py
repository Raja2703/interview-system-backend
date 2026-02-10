# apps/notifications/consumers.py
"""
WebSocket consumer for real-time notifications.

Provides:
- NotificationConsumer: Handles WebSocket connections for notification delivery
- Automatic channel group management based on user authentication
- Real-time notification delivery to connected clients
"""
import json
import logging
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth.models import AnonymousUser

logger = logging.getLogger(__name__)


class NotificationConsumer(AsyncWebsocketConsumer):
    """
    WebSocket consumer for real-time notifications.
    
    Connection URL: ws://host/ws/notifications/
    
    Features:
    - Authenticated connections only
    - Automatic group subscription based on user
    - Real-time notification delivery
    - Connection state management
    
    Client Messages:
    - {"type": "ping"} - Health check, returns {"type": "pong"}
    - {"type": "mark_read", "notification_id": "uuid"} - Mark notification as read
    
    Server Messages:
    - {"type": "notification", "notification": {...}} - New notification
    - {"type": "unread_count", "count": N} - Updated unread count
    """
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.group_name = None
        self.user = None
    
    async def connect(self):
        """
        Handle WebSocket connection.
        
        Authenticates user and subscribes to notification channel group.
        Rejects unauthenticated connections.
        """
        self.user = self.scope.get('user')
        
        # Reject anonymous connections
        if isinstance(self.user, AnonymousUser) or not self.user or not self.user.is_authenticated:
            logger.warning("Rejected unauthenticated WebSocket connection")
            await self.close(code=4001)
            return
        
        # Build group name based on user
        self.group_name = await self._get_group_name()
        
        # Join the notification group
        await self.channel_layer.group_add(
            self.group_name,
            self.channel_name
        )
        
        # Accept the connection
        await self.accept()
        
        logger.info(f"WebSocket connected: {self.user.email} -> {self.group_name}")
        
        # Send initial unread count
        unread_count = await self._get_unread_count()
        await self.send(json.dumps({
            'type': 'unread_count',
            'count': unread_count
        }))
    
    async def disconnect(self, close_code):
        """
        Handle WebSocket disconnection.
        
        Removes user from notification channel group.
        """
        if self.group_name:
            await self.channel_layer.group_discard(
                self.group_name,
                self.channel_name
            )
            logger.info(f"WebSocket disconnected: {self.group_name} (code: {close_code})")
    
    async def receive(self, text_data):
        """
        Handle incoming WebSocket messages from client.
        
        Supported message types:
        - ping: Health check
        - mark_read: Mark a notification as read
        """
        try:
            data = json.loads(text_data)
            message_type = data.get('type')
            
            if message_type == 'ping':
                await self.send(json.dumps({'type': 'pong'}))
            
            elif message_type == 'mark_read':
                notification_id = data.get('notification_id')
                if notification_id:
                    success = await self._mark_notification_read(notification_id)
                    if success:
                        # Send updated unread count
                        unread_count = await self._get_unread_count()
                        await self.send(json.dumps({
                            'type': 'unread_count',
                            'count': unread_count
                        }))
            
            elif message_type == 'get_unread_count':
                unread_count = await self._get_unread_count()
                await self.send(json.dumps({
                    'type': 'unread_count',
                    'count': unread_count
                }))
            
        except json.JSONDecodeError:
            logger.warning("Invalid JSON received on WebSocket")
        except Exception as e:
            logger.error(f"Error handling WebSocket message: {str(e)}")
    
    async def notification_send(self, event):
        """
        Handle notification.send events from channel layer.
        
        Sends the notification to the WebSocket client.
        """
        notification = event.get('notification')
        
        await self.send(json.dumps({
            'type': 'notification',
            'notification': notification
        }))
        
        # Also send updated unread count
        unread_count = await self._get_unread_count()
        await self.send(json.dumps({
            'type': 'unread_count',
            'count': unread_count
        }))
    
    # ========== DATABASE OPERATIONS ==========
    
    @database_sync_to_async
    def _get_group_name(self):
        """Get the notification channel group name for the user."""
        if hasattr(self.user, 'profile') and self.user.profile.public_id:
            return f"notifications_{self.user.profile.public_id}"
        return f"notifications_user_{self.user.id}"
    
    @database_sync_to_async
    def _get_unread_count(self):
        """Get unread notification count for the user."""
        from .models import Notification
        return Notification.get_unread_count(self.user)
    
    @database_sync_to_async
    def _mark_notification_read(self, notification_id):
        """Mark a notification as read."""
        from .models import Notification
        try:
            notification = Notification.objects.get(
                id=notification_id,
                recipient=self.user
            )
            notification.mark_as_read()
            return True
        except Notification.DoesNotExist:
            return False
