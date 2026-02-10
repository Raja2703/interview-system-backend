# apps/notifications/services.py
"""
Notification Service for the Interview Platform.

Provides:
- Notification creation methods for each interview event
- WebSocket delivery functionality
- Notification message templates
"""
import logging
from django.conf import settings
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync

from .models import Notification

logger = logging.getLogger(__name__)


class NotificationService:
    """
    Service class for managing notifications.
    
    Handles notification creation and delivery for:
    - Interview created
    - Interview accepted
    - Interview rejected
    - Interview completed
    - Interview not attended
    - Interview cancelled
    """
    
    # ========== NOTIFICATION CREATORS ==========
    
    @classmethod
    def notify_interview_created(cls, interview_request):
        """
        Send notification when a new interview request is created.
        
        Recipient: Receiver (taker/interviewer)
        Actor: Sender (attender/interviewee)
        """
        sender = interview_request.sender
        receiver = interview_request.receiver
        
        sender_name = cls._get_user_name(sender)
        scheduled_time = interview_request.scheduled_time.strftime("%B %d, %Y at %I:%M %p")
        
        notification = Notification.create_notification(
            recipient=receiver,
            actor=sender,
            notification_type=Notification.TYPE_INTERVIEW_CREATED,
            title="New Interview Request",
            message=f"{sender_name} has requested an interview with you scheduled for {scheduled_time}.",
            interview_request=interview_request,
            metadata={
                'sender_id': str(sender.profile.public_id) if hasattr(sender, 'profile') else None,
                'scheduled_time': interview_request.scheduled_time.isoformat(),
                'topic': interview_request.topic or 'General Interview',
            }
        )
        
        logger.info(f"Notification sent: interview_created -> {receiver.email}")
        return notification
    
    @classmethod
    def notify_interview_accepted(cls, interview_request):
        """
        Send notification when an interview request is accepted.
        
        Recipient: Sender (attender/interviewee)
        Actor: Receiver (taker/interviewer)
        """
        sender = interview_request.sender
        receiver = interview_request.receiver
        
        receiver_name = cls._get_user_name(receiver)
        scheduled_time = interview_request.scheduled_time.strftime("%B %d, %Y at %I:%M %p")
        
        notification = Notification.create_notification(
            recipient=sender,
            actor=receiver,
            notification_type=Notification.TYPE_INTERVIEW_ACCEPTED,
            title="Interview Request Accepted",
            message=f"{receiver_name} has accepted your interview request. The interview is scheduled for {scheduled_time}.",
            interview_request=interview_request,
            metadata={
                'receiver_id': str(receiver.profile.public_id) if hasattr(receiver, 'profile') else None,
                'scheduled_time': interview_request.scheduled_time.isoformat(),
                'join_url': f"/api/interviews/{interview_request.uuid_id}/join/",
            }
        )
        
        logger.info(f"Notification sent: interview_accepted -> {sender.email}")
        return notification
    
    @classmethod
    def notify_interview_rejected(cls, interview_request):
        """
        Send notification when an interview request is rejected.
        
        Recipient: Sender (attender/interviewee)
        Actor: Receiver (taker/interviewer)
        """
        sender = interview_request.sender
        receiver = interview_request.receiver
        
        receiver_name = cls._get_user_name(receiver)
        reason = interview_request.rejection_reason or "No reason provided"
        
        notification = Notification.create_notification(
            recipient=sender,
            actor=receiver,
            notification_type=Notification.TYPE_INTERVIEW_REJECTED,
            title="Interview Request Declined",
            message=f"{receiver_name} has declined your interview request. Reason: {reason}",
            interview_request=interview_request,
            metadata={
                'receiver_id': str(receiver.profile.public_id) if hasattr(receiver, 'profile') else None,
                'rejection_reason': reason,
            }
        )
        
        logger.info(f"Notification sent: interview_rejected -> {sender.email}")
        return notification
    
    @classmethod
    def notify_interview_completed(cls, interview_request, completed_by):
        """
        Send notification when an interview is marked as completed.
        
        Recipients: Both participants
        Actor: User who marked it completed (taker only)
        """
        sender = interview_request.sender
        receiver = interview_request.receiver
        
        completed_by_name = cls._get_user_name(completed_by)
        notifications = []
        
        # Notify the other participant
        other_user = sender if completed_by == receiver else receiver
        
        notification = Notification.create_notification(
            recipient=other_user,
            actor=completed_by,
            notification_type=Notification.TYPE_INTERVIEW_COMPLETED,
            title="Interview Completed",
            message=f"Your interview has been marked as completed by {completed_by_name}.",
            interview_request=interview_request,
            metadata={
                'completed_by_id': str(completed_by.profile.public_id) if hasattr(completed_by, 'profile') else None,
                'completed_at': interview_request.completed_at.isoformat() if interview_request.completed_at else None,
            }
        )
        notifications.append(notification)
        
        logger.info(f"Notification sent: interview_completed -> {other_user.email}")
        return notifications
    
    @classmethod
    def notify_interview_not_attended(cls, interview_request, marked_by=None):
        """
        Send notification when an interview is marked as not attended.
        
        Recipients: Both participants
        Actor: User who marked it (taker) or system (auto-finalize)
        """
        sender = interview_request.sender
        receiver = interview_request.receiver
        
        is_auto = marked_by is None
        
        notifications = []
        
        # Notify both participants
        for user in [sender, receiver]:
            if is_auto:
                message = "Your interview was marked as not attended because the time window has expired."
            else:
                marked_by_name = cls._get_user_name(marked_by)
                message = f"Your interview was marked as not attended by {marked_by_name}."
            
            notification = Notification.create_notification(
                recipient=user,
                actor=marked_by,
                notification_type=Notification.TYPE_INTERVIEW_NOT_ATTENDED,
                title="Interview Not Attended",
                message=message,
                interview_request=interview_request,
                metadata={
                    'is_auto_finalized': is_auto,
                    'marked_by_id': str(marked_by.profile.public_id) if marked_by and hasattr(marked_by, 'profile') else None,
                }
            )
            notifications.append(notification)
            logger.info(f"Notification sent: interview_not_attended -> {user.email}")
        
        return notifications
    
    @classmethod
    def notify_interview_cancelled(cls, interview_request, cancelled_by):
        """
        Send notification when an interview is cancelled.
        
        Recipient: The other participant
        Actor: User who cancelled
        """
        sender = interview_request.sender
        receiver = interview_request.receiver
        
        cancelled_by_name = cls._get_user_name(cancelled_by)
        reason = interview_request.rejection_reason or "No reason provided"
        
        # Notify the other participant
        other_user = sender if cancelled_by == receiver else receiver
        
        notification = Notification.create_notification(
            recipient=other_user,
            actor=cancelled_by,
            notification_type=Notification.TYPE_INTERVIEW_CANCELLED,
            title="Interview Cancelled",
            message=f"Your interview with {cancelled_by_name} has been cancelled. Reason: {reason}",
            interview_request=interview_request,
            metadata={
                'cancelled_by_id': str(cancelled_by.profile.public_id) if hasattr(cancelled_by, 'profile') else None,
                'cancellation_reason': reason,
            }
        )
        
        logger.info(f"Notification sent: interview_cancelled -> {other_user.email}")
        return notification
    
    # ========== WEBSOCKET DELIVERY ==========
    
    @classmethod
    def send_websocket_notification(cls, notification):
        """
        Send notification via WebSocket to the recipient.
        
        Uses Django Channels to deliver real-time notifications.
        """
        try:
            channel_layer = get_channel_layer()
            
            if channel_layer is None:
                logger.warning("Channel layer not configured. WebSocket notification not sent.")
                return False
            
            from .serializers import NotificationWebSocketSerializer
            
            # Serialize the notification
            serializer = NotificationWebSocketSerializer(notification)
            
            # Build the WebSocket message
            message = {
                'type': 'notification.send',
                'notification': serializer.data,
            }
            
            # Send to user's notification channel group
            group_name = cls._get_user_channel_group(notification.recipient)
            
            async_to_sync(channel_layer.group_send)(
                group_name,
                message
            )
            
            logger.debug(f"WebSocket notification sent to group: {group_name}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send WebSocket notification: {str(e)}")
            return False
    
    # ========== HELPER METHODS ==========
    
    @classmethod
    def _get_user_name(cls, user):
        """Get display name for a user."""
        if hasattr(user, 'profile') and user.profile.name:
            return user.profile.name
        return user.username or user.email
    
    @classmethod
    def _get_user_channel_group(cls, user):
        """
        Get the WebSocket channel group name for a user.
        
        Format: notifications_{user_public_id}
        """
        if hasattr(user, 'profile') and user.profile.public_id:
            return f"notifications_{user.profile.public_id}"
        return f"notifications_user_{user.id}"
