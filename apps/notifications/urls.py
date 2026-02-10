# apps/notifications/urls.py
"""
URL configuration for notifications app.

Endpoints:
- GET  /api/notifications/              - List notifications
- GET  /api/notifications/{id}/         - Get notification detail
- DELETE /api/notifications/{id}/       - Delete notification
- POST /api/notifications/mark-read/    - Mark as read
- GET  /api/notifications/unread-count/ - Get unread count
"""
from django.urls import path
from . import api

app_name = 'notifications'

urlpatterns = [
    # List notifications
    path('', api.NotificationListAPI.as_view(), name='notification_list'),
    
    # Mark notifications as read
    path('mark-read/', api.NotificationMarkReadAPI.as_view(), name='notification_mark_read'),
    
    # Get unread count
    path('unread-count/', api.NotificationUnreadCountAPI.as_view(), name='notification_unread_count'),
    
    # Notification detail and delete
    path('<uuid:id>/', api.NotificationDetailAPI.as_view(), name='notification_detail'),
]
