# apps/notifications/admin.py
"""
Django admin configuration for Notifications.
"""
from django.contrib import admin
from .models import Notification


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    """Admin configuration for Notification model."""
    
    list_display = [
        'id',
        'recipient',
        'notification_type',
        'title',
        'is_read',
        'created_at',
    ]
    list_filter = [
        'notification_type',
        'is_read',
        'created_at',
    ]
    search_fields = [
        'recipient__email',
        'recipient__username',
        'title',
        'message',
    ]
    readonly_fields = [
        'id',
        'created_at',
        'updated_at',
        'read_at',
    ]
    ordering = ['-created_at']
    
    fieldsets = (
        (None, {
            'fields': ('id', 'recipient', 'actor', 'notification_type')
        }),
        ('Content', {
            'fields': ('title', 'message', 'metadata')
        }),
        ('Related Objects', {
            'fields': ('interview_request',)
        }),
        ('Status', {
            'fields': ('is_read', 'read_at')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
