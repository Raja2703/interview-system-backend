# apps/notifications/models.py
"""
Notification model for the Interview Platform.

Stores all notifications with:
- Notification types for different events
- Read/unread status tracking
- Reference to interview requests
- JSON metadata for flexible data storage
"""
from django.db import models
from django.conf import settings
from django.utils import timezone
import uuid

User = settings.AUTH_USER_MODEL


class Notification(models.Model):
    """
    Notification model for interview-related events.
    
    Notification Types:
    - interview_created: New interview request received
    - interview_accepted: Interview request was accepted
    - interview_rejected: Interview request was rejected  
    - interview_completed: Interview was marked as completed
    - interview_not_attended: Interview was marked as not attended
    - interview_cancelled: Interview was cancelled
    
    Delivery:
    - Stored in database for persistence
    - Delivered via WebSocket for real-time updates
    """
    
    # Notification Type Choices
    TYPE_INTERVIEW_CREATED = 'interview_created'
    TYPE_INTERVIEW_ACCEPTED = 'interview_accepted'
    TYPE_INTERVIEW_REJECTED = 'interview_rejected'
    TYPE_INTERVIEW_COMPLETED = 'interview_completed'
    TYPE_INTERVIEW_NOT_ATTENDED = 'interview_not_attended'
    TYPE_INTERVIEW_CANCELLED = 'interview_cancelled'
    
    TYPE_CHOICES = (
        (TYPE_INTERVIEW_CREATED, 'Interview Created'),
        (TYPE_INTERVIEW_ACCEPTED, 'Interview Accepted'),
        (TYPE_INTERVIEW_REJECTED, 'Interview Rejected'),
        (TYPE_INTERVIEW_COMPLETED, 'Interview Completed'),
        (TYPE_INTERVIEW_NOT_ATTENDED, 'Interview Not Attended'),
        (TYPE_INTERVIEW_CANCELLED, 'Interview Cancelled'),
    )
    
    # Primary key as UUID for API safety
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False
    )
    
    # Recipient of the notification
    recipient = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='notifications',
        help_text='User who receives this notification'
    )
    
    # Actor who triggered the notification (optional)
    actor = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='triggered_notifications',
        help_text='User who triggered this notification'
    )
    
    # Notification type
    notification_type = models.CharField(
        max_length=50,
        choices=TYPE_CHOICES,
        db_index=True,
        help_text='Type of notification'
    )
    
    # Notification title and message
    title = models.CharField(
        max_length=200,
        help_text='Notification title'
    )
    
    message = models.TextField(
        help_text='Notification message/body'
    )
    
    # Reference to interview request (optional for flexibility)
    interview_request = models.ForeignKey(
        'interviews.InterviewRequest',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='notifications',
        help_text='Related interview request'
    )
    
    # Additional metadata (JSON)
    metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text='Additional notification data in JSON format'
    )
    
    # Read status
    is_read = models.BooleanField(
        default=False,
        db_index=True,
        help_text='Whether the notification has been read'
    )
    
    read_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text='When the notification was read'
    )
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['recipient', 'is_read', '-created_at']),
            models.Index(fields=['recipient', 'notification_type']),
        ]
        verbose_name = 'Notification'
        verbose_name_plural = 'Notifications'
    
    def __str__(self):
        return f"{self.notification_type} -> {self.recipient} ({self.created_at})"
    
    def mark_as_read(self):
        """Mark notification as read."""
        if not self.is_read:
            self.is_read = True
            self.read_at = timezone.now()
            self.save(update_fields=['is_read', 'read_at', 'updated_at'])
    
    def mark_as_unread(self):
        """Mark notification as unread."""
        if self.is_read:
            self.is_read = False
            self.read_at = None
            self.save(update_fields=['is_read', 'read_at', 'updated_at'])
    
    @classmethod
    def create_notification(
        cls,
        recipient,
        notification_type,
        title,
        message,
        actor=None,
        interview_request=None,
        metadata=None,
        send_websocket=True
    ):
        """
        Create a new notification and optionally send via WebSocket.
        
        Args:
            recipient: User to receive the notification
            notification_type: Type of notification
            title: Notification title
            message: Notification message
            actor: User who triggered the notification (optional)
            interview_request: Related interview request (optional)
            metadata: Additional data (optional)
            send_websocket: Whether to send via WebSocket (default: True)
        
        Returns:
            Notification: The created notification instance
        """
        notification = cls.objects.create(
            recipient=recipient,
            actor=actor,
            notification_type=notification_type,
            title=title,
            message=message,
            interview_request=interview_request,
            metadata=metadata or {}
        )
        
        # Send via WebSocket if enabled
        if send_websocket:
            from apps.notifications.services import NotificationService
            NotificationService.send_websocket_notification(notification)
        
        return notification
    
    @classmethod
    def get_unread_count(cls, user):
        """Get count of unread notifications for a user."""
        return cls.objects.filter(recipient=user, is_read=False).count()
    
    @classmethod
    def mark_all_as_read(cls, user):
        """Mark all notifications as read for a user."""
        now = timezone.now()
        return cls.objects.filter(
            recipient=user,
            is_read=False
        ).update(
            is_read=True,
            read_at=now,
            updated_at=now
        )
