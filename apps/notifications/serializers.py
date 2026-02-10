# apps/notifications/serializers.py
"""
Serializers for Notification model.

Provides:
- NotificationSerializer: Full notification details
- NotificationListSerializer: Compact list view
- NotificationMarkReadSerializer: For mark-as-read actions
"""
from rest_framework import serializers
from .models import Notification


class NotificationSerializer(serializers.ModelSerializer):
    """
    Full serializer for Notification model.
    
    Includes all fields with nested actor and interview details.
    """
    
    actor_id = serializers.UUIDField(
        source='actor.profile.public_id',
        read_only=True,
        allow_null=True
    )
    actor_name = serializers.CharField(
        source='actor.profile.name',
        read_only=True,
        allow_null=True
    )
    actor_profile_picture = serializers.URLField(
        source='actor.profile.profile_picture_url',
        read_only=True,
        allow_null=True
    )
    interview_id = serializers.UUIDField(
        source='interview_request.uuid_id',
        read_only=True,
        allow_null=True
    )
    interview_status = serializers.CharField(
        source='interview_request.status',
        read_only=True,
        allow_null=True
    )
    
    class Meta:
        model = Notification
        fields = [
            'id',
            'notification_type',
            'title',
            'message',
            'actor_id',
            'actor_name',
            'actor_profile_picture',
            'interview_id',
            'interview_status',
            'metadata',
            'is_read',
            'read_at',
            'created_at',
        ]
        read_only_fields = fields


class NotificationListSerializer(serializers.ModelSerializer):
    """
    Compact serializer for notification list view.
    
    Excludes metadata and some nested details for performance.
    """
    
    actor_name = serializers.CharField(
        source='actor.profile.name',
        read_only=True,
        allow_null=True
    )
    interview_id = serializers.UUIDField(
        source='interview_request.uuid_id',
        read_only=True,
        allow_null=True
    )
    
    class Meta:
        model = Notification
        fields = [
            'id',
            'notification_type',
            'title',
            'message',
            'actor_name',
            'interview_id',
            'is_read',
            'created_at',
        ]
        read_only_fields = fields


class NotificationMarkReadSerializer(serializers.Serializer):
    """
    Serializer for marking notifications as read.
    
    Accepts a list of notification IDs to mark as read.
    """
    
    notification_ids = serializers.ListField(
        child=serializers.UUIDField(),
        required=False,
        help_text='List of notification IDs to mark as read. If empty, marks all as read.'
    )
    
    mark_all = serializers.BooleanField(
        default=False,
        help_text='If true, marks all notifications as read.'
    )


class NotificationWebSocketSerializer(serializers.ModelSerializer):
    """
    Serializer for WebSocket notification delivery.
    
    Minimal data optimized for real-time delivery.
    """
    
    actor_name = serializers.CharField(
        source='actor.profile.name',
        read_only=True,
        allow_null=True
    )
    interview_id = serializers.UUIDField(
        source='interview_request.uuid_id',
        read_only=True,
        allow_null=True
    )
    
    class Meta:
        model = Notification
        fields = [
            'id',
            'notification_type',
            'title',
            'message',
            'actor_name',
            'interview_id',
            'metadata',
            'created_at',
        ]
        read_only_fields = fields
