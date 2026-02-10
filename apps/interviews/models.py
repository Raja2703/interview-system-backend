# apps/interviews/models.py
"""
Interview Request and LiveKit Room models for the interview system.

Models:
- InterviewRequest: Full lifecycle management for interview requests
- LiveKitRoom: Lazily created rooms for accepted interviews

Security:
- UUID field for public-safe endpoints (uuid_id)
- Strict status transitions
- Audit timestamps
"""
from django.db import models, transaction
from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.db.models import Q,F,ExpressionWrapper,DateTimeField
import uuid

User = settings.AUTH_USER_MODEL


class InterviewRequest(models.Model):
    """
    Interview Request model with full lifecycle management.
    
    Lifecycle:
        pending -> accepted -> completed
        pending -> rejected
        pending -> cancelled (by sender only)
        pending -> expired (auto, based on time window)
    
    Rules:
        - Only ATTENDER can send interview requests
        - Only TAKER can accept/reject
        - Sender cannot be receiver
        - Only one active request per pair (pending/accepted)
        - Cancel allowed only by sender
        - Accept creates LiveKit room lazily
    """
    
    STATUS_PENDING = 'pending'
    STATUS_ACCEPTED = 'accepted'
    STATUS_REJECTED = 'rejected'
    STATUS_CANCELLED = 'cancelled'
    STATUS_COMPLETED = 'completed'
    STATUS_NOT_ATTENDED = 'not attended'
    STATUS_NOT_CONDUCTED = 'not_conducted'  # New: Auto-expiry when participants don't join
    
    STATUS_CHOICES = (
        (STATUS_PENDING, 'Pending'),
        (STATUS_ACCEPTED, 'Accepted'),
        (STATUS_REJECTED, 'Rejected'),
        (STATUS_CANCELLED, 'Cancelled'),
        (STATUS_COMPLETED, 'Completed'),
        (STATUS_NOT_ATTENDED, 'Not attended'),
        (STATUS_NOT_CONDUCTED, 'Not Conducted'),  # Auto-expiry status
    )
    
    # Active statuses that prevent duplicate requests
    ACTIVE_STATUSES = [STATUS_PENDING, STATUS_ACCEPTED]
    
    # Keep integer auto primary key for migration compatibility
    # id = models.AutoField(primary_key=True) - Django default
    
    # UUID for public-safe API exposure (indexed, unique)
    uuid_id = models.UUIDField(
        default=uuid.uuid4,
        editable=False,
        unique=True,
        db_index=True,
        help_text='UUID for API-safe exposure'
    )
    
    # Sender (Interview Attender - the person requesting the interview)
    sender = models.ForeignKey(
        User, 
        related_name='sent_interview_requests', 
        on_delete=models.CASCADE,
        help_text='User who sent the request (must be ATTENDER)'
    )
    
    # Receiver (Interview Taker - the interviewer)
    receiver = models.ForeignKey(
        User, 
        related_name='received_interview_requests', 
        on_delete=models.CASCADE,
        help_text='User who receives the request (must be TAKER)'
    )

    # Scheduled interview time
    scheduled_time = models.DateTimeField(
        help_text='Scheduled date and time for the interview'
    )
    
    # Interview duration in minutes (default: 60)
    duration_minutes = models.PositiveIntegerField(
        default=60,
        help_text='Interview duration in minutes'
    )
    
    # Message from sender to receiver
    message = models.TextField(
        blank=True,
        default='',
        help_text='Optional message from sender to receiver'
    )
    
    # Interview topic/focus
    topic = models.CharField(
        max_length=200,
        blank=True,
        default='',
        help_text='Interview topic or focus area'
    )
    ACTIVE_STATUSES = [STATUS_PENDING, STATUS_ACCEPTED]
    # Status with lifecycle management
    status = models.CharField(
        max_length=20, 
        choices=STATUS_CHOICES, 
        default=STATUS_PENDING,
        db_index=True
    )
    
    # Rejection/cancellation reason
    rejection_reason = models.TextField(
        blank=True,
        default='',
        help_text='Reason for rejection or cancellation'
    )
    
    # Credits involved (for interviewer payment)
    credits = models.PositiveIntegerField(
        default=0,
        help_text='Credits for this interview (from interviewer profile)'
    )
    
    # Audit timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    accepted_at = models.DateTimeField(null=True, blank=True)
    rejected_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    expired_at = models.DateTimeField(null=True, blank=True)
    
    # Attendance tracking for proper finalization logic
    sender_joined_at = models.DateTimeField(
        null=True, 
        blank=True,
        help_text='When the sender (attender) joined the interview room'
    )
    receiver_joined_at = models.DateTimeField(
        null=True, 
        blank=True,
        help_text='When the receiver (taker) joined the interview room'
    )

    


    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['sender', 'receiver', 'status']),
            models.Index(fields=['status', 'scheduled_time']),
            models.Index(fields=['receiver', 'status']),
            # New index for Celery expiry task: efficiently query accepted interviews by scheduled_time
            models.Index(fields=['status', 'accepted_at'], name='idx_interview_expiry_check'),
        ]
    
    def __str__(self):
        return f"{self.sender} → {self.receiver} ({self.status})"
    
    def clean(self):
        """Validate interview request constraints."""
        # Sender cannot be receiver
        if self.sender_id and self.receiver_id and self.sender_id == self.receiver_id:
            raise ValidationError("Sender cannot be the same as receiver.")
        
        # Scheduled time must be in the future (for new requests)
        if not self.pk and self.scheduled_time:
            if self.scheduled_time <= timezone.now():
                raise ValidationError("Scheduled time must be in the future.")
    
    # ========== STATE MACHINE ==========
    # Centralized status transition rules to prevent illegal transitions
    # Format: {from_status: [allowed_to_statuses]}
    VALID_TRANSITIONS = {
        STATUS_PENDING: [STATUS_ACCEPTED, STATUS_REJECTED, STATUS_CANCELLED, STATUS_NOT_CONDUCTED],
        STATUS_ACCEPTED: [STATUS_COMPLETED, STATUS_CANCELLED, STATUS_NOT_ATTENDED, STATUS_NOT_CONDUCTED],
        # Terminal states - no transitions allowed
        STATUS_REJECTED: [],
        STATUS_CANCELLED: [],
        STATUS_COMPLETED: [],
        STATUS_NOT_ATTENDED: [],
        STATUS_NOT_CONDUCTED: [],
    }
    
    def _validate_transition(self, new_status: str) -> bool:
        """
        Validate if a status transition is allowed.
        
        Args:
            new_status: The status to transition to
            
        Returns:
            bool: True if transition is valid
            
        Raises:
            ValidationError: If transition is not allowed
        """
        allowed = self.VALID_TRANSITIONS.get(self.status, [])
        if new_status not in allowed:
            raise ValidationError(
                f"Invalid status transition: '{self.status}' → '{new_status}'. "
                f"Allowed transitions from '{self.status}': {allowed or 'none (terminal state)'}"
            )
        return True
    
    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)
    
    # ========== STATUS TRANSITION METHODS ==========
    
    def accept(self):
        """Accept the interview request (TAKER only)."""
        self._validate_transition(self.STATUS_ACCEPTED)
        
        self.status = self.STATUS_ACCEPTED
        self.accepted_at = timezone.now()
        self.save(update_fields=['status', 'accepted_at', 'updated_at'])
        
        # Create LiveKit room lazily
        self._create_livekit_room()
        
        return self
    
    def reject(self, reason=''):
        """Reject the interview request (TAKER only)."""
        self._validate_transition(self.STATUS_REJECTED)
        
        self.status = self.STATUS_REJECTED
        self.rejected_at = timezone.now()
        self.rejection_reason = reason
        self.save(update_fields=['status', 'rejected_at', 'rejection_reason', 'updated_at'])
        
        return self
    
    def cancel(self, reason=''):
        """Cancel the interview request (SENDER only, or ADMIN)."""
        self._validate_transition(self.STATUS_CANCELLED)
        
        self.status = self.STATUS_CANCELLED
        self.cancelled_at = timezone.now()
        self.rejection_reason = reason
        self.save(update_fields=['status', 'cancelled_at', 'rejection_reason', 'updated_at'])
        
        return self
    
    def complete(self):
        """
        Mark interview as completed (internal method).
        Use mark_completed_by_taker() for API-level completion with user validation.
        """
        self._validate_transition(self.STATUS_COMPLETED)
        
        self.status = self.STATUS_COMPLETED
        self.completed_at = timezone.now()
        self.save(update_fields=['status', 'completed_at', 'updated_at'])
        
        # Deactivate LiveKit room
        self._deactivate_livekit_room()
        
        return self
    
    def mark_completed_by_taker(self, user):
        """
        Mark interview as completed (TAKER only).
        
        Only the taker (receiver/interviewer) can mark an interview as completed.
        This is the API-level method that should be called from views.
        
        Args:
            user: The user attempting to mark as completed
            
        Raises:
            ValidationError: If user is not the taker or status is invalid
        """
        if user != self.receiver:
            raise ValidationError("Only the interviewer (taker) can mark an interview as completed.")
        
        return self.complete()
    
    def mark_not_attended(self):
        """
        Mark interview as not attended (internal method).
        Use mark_not_attended_by_taker() for API-level marking with user validation.
        """
        self._validate_transition(self.STATUS_NOT_ATTENDED)
        
        self.status = self.STATUS_NOT_ATTENDED
        self.expired_at = timezone.now()
        self.save(update_fields=['status', 'expired_at', 'updated_at'])
        
        # Deactivate LiveKit room
        self._deactivate_livekit_room()
        
        return self
    
    def mark_not_attended_by_taker(self, user):
        """
        Mark interview as not attended (TAKER only).
        
        Only the taker (receiver/interviewer) can mark an interview as not attended.
        This is the API-level method that should be called from views.
        
        Args:
            user: The user attempting to mark as not attended
            
        Raises:
            ValidationError: If user is not the taker or status is invalid
        """
        if user != self.receiver:
            raise ValidationError("Only the interviewer (taker) can mark an interview as not attended.")
        
        return self.mark_not_attended()
    
    def _deactivate_livekit_room(self):
        """Deactivate LiveKit room when interview ends."""
        try:
            if hasattr(self, 'livekit_room') and self.livekit_room:
                self.livekit_room.end_room()
        except Exception:
            pass  # Room might not exist
    
    def expire(self):
        """
        Mark interview as expired (for pending requests past scheduled time).
        Uses not_conducted status since the interview never took place.
        """
        self._validate_transition(self.STATUS_NOT_CONDUCTED)
        
        self.status = self.STATUS_NOT_CONDUCTED
        self.expired_at = timezone.now()
        self.save(update_fields=['status', 'expired_at', 'updated_at'])
        
        return self
    
    # ========== LIVEKIT ROOM MANAGEMENT ==========
    
    def _create_livekit_room(self):
        """Create LiveKit room for accepted interview."""
        if self.status != self.STATUS_ACCEPTED:
            return None
        
        room, created = LiveKitRoom.objects.get_or_create(
            interview_request=self,
            defaults={
                'room_name': f"interview-{self.uuid_id}",
            }
        )
        return room
    
    def get_livekit_room(self):
        """Get LiveKit room if exists and interview is accepted."""
        if self.status != self.STATUS_ACCEPTED:
            return None
        try:
            return self.livekit_room
        except LiveKitRoom.DoesNotExist:
            return self._create_livekit_room()
    
    # ========== VALIDATION HELPERS ==========
    
    def is_active(self):
        """Check if request is in an active state."""
        return self.status in self.ACTIVE_STATUSES
    
    def is_joinable(self):
        """Check if the interview can be joined."""
        if self.status != self.STATUS_ACCEPTED:
            return False
        
        #now = timezone.now()
        now = timezone.now().astimezone(timezone.UTC)

        # Allow joining 15 minutes before scheduled time until end of duration
        join_window_start = self.scheduled_time - timezone.timedelta(minutes=15)
        join_window_end = self.scheduled_time + timezone.timedelta(minutes=self.duration_minutes + 30)
        
        return join_window_start <= now <= join_window_end
    
    def get_time_window_status(self):
        """Get the current status of the interview time window."""
        if self.status != self.STATUS_ACCEPTED:
            return 'not_accepted'
        
        #now = timezone.now()
        now = timezone.now().astimezone(timezone.UTC)
        
        join_window_start = self.scheduled_time - timezone.timedelta(minutes=15)
        join_window_end = self.scheduled_time + timezone.timedelta(minutes=self.duration_minutes + 30)
        
        if now < join_window_start:
            return 'too_early'
        elif now > join_window_end:
            return 'too_late'
        else:
            return 'joinable'
    
    def finalize_if_expired(self):
        """
        Called by Celery periodic task to auto-finalize interviews.
        
        Implements 20-minute auto-expiry logic:
        - If NEITHER participant joins within 20 minutes of scheduled_time → not_conducted
        - If ONLY ONE participant joins and 20 minutes pass → not_conducted
        - If BOTH participants joined → completed (when time window ends)
        
        Also handles the case where time window has fully expired.
        
        Returns:
            bool: True if interview was finalized, False otherwise
        """
        import logging
        from django.db import transaction
        
        logger = logging.getLogger('apps.interviews.finalize')
        
        if self.status != self.STATUS_ACCEPTED:
            return False

        from .utils import get_interview_time_window
        from django.utils import timezone

        now = timezone.now()
        window = get_interview_time_window(
            self.scheduled_time,
            self.duration_minutes
        )
        
        # Get attendance from both model fields and LiveKitRoom
        room = getattr(self, "livekit_room", None)
        
        # Check attendance - prioritize InterviewRequest fields, fallback to room
        sender_joined = self.sender_joined_at or (room and room.sender_joined_at)
        receiver_joined = self.receiver_joined_at or (room and room.receiver_joined_at)
        
        # Calculate 20-minute mark from scheduled time
        expiry_threshold = self.scheduled_time + timezone.timedelta(minutes=20)
        
        # Scenario 1: 20 minutes passed since scheduled_time
        if now >= expiry_threshold:
            # Check if NEITHER participant joined
            if not sender_joined and not receiver_joined:
                return self._mark_not_conducted(
                    reason='neither_joined',
                    logger=logger
                )
            
            # Check if ONLY ONE participant joined (waiting for the other)
            if bool(sender_joined) != bool(receiver_joined):
                return self._mark_not_conducted(
                    reason='partial_attendance',
                    logger=logger
                )
        
        # Scenario 2: Time window has fully expired
        if now > window["join_end"]:
            if sender_joined and receiver_joined:
                # Both joined - mark as completed
                return self._mark_completed_auto(logger=logger)
            else:
                # At least one didn't join by end of window
                return self._mark_not_conducted(
                    reason='window_expired',
                    logger=logger
                )
        
        # Interview is still active, no action needed
        return False
    
    def _mark_not_conducted(self, reason: str, logger=None):
        """
        Internal method to mark interview as not_conducted with atomic transaction.
        
        Args:
            reason: Why the interview was not conducted (for logging)
            logger: Logger instance for structured logging
        """
        from django.db import transaction
        from django.utils import timezone
        
        if logger:
            logger.info(
                f"[INTERVIEW_NOT_CONDUCTED] interview={self.uuid_id} "
                f"reason={reason} sender_joined={bool(self.sender_joined_at)} "
                f"receiver_joined={bool(self.receiver_joined_at)} "
                f"scheduled_time={self.scheduled_time.isoformat()}"
            )
        
        with transaction.atomic():
            self.status = self.STATUS_NOT_CONDUCTED
            self.expired_at = timezone.now()
            self.save(update_fields=["status", "expired_at", "updated_at"])
            
            # Deactivate LiveKit room
            self._deactivate_livekit_room()
            
            # Create audit log entry (system action - no user)
            InterviewAuditLog.objects.create(
                interview_request=self,
                user=None,  # System action
                action=InterviewAuditLog.ACTION_NOT_CONDUCTED,
                details={
                    'reason': reason,
                    'sender_joined': bool(self.sender_joined_at),
                    'receiver_joined': bool(self.receiver_joined_at),
                    'auto_finalized': True,
                }
            )
        
        # Send notification (outside transaction to avoid blocking)
        try:
            from apps.notifications.services import NotificationService
            NotificationService.notify_interview_not_conducted(self, reason=reason)
        except (ImportError, AttributeError):
            pass  # Notifications app not installed or method doesn't exist
        
        return True
    
    def _mark_completed_auto(self, logger=None):
        """
        Internal method to mark interview as completed automatically.
        Called when time window expires and both participants attended.
        """
        from django.db import transaction
        from django.utils import timezone
        
        if logger:
            logger.info(
                f"[INTERVIEW_COMPLETED] interview={self.uuid_id} "
                f"auto_finalized=true sender_joined={self.sender_joined_at} "
                f"receiver_joined={self.receiver_joined_at}"
            )
        
        with transaction.atomic():
            self.status = self.STATUS_COMPLETED
            self.completed_at = timezone.now()
            self.save(update_fields=["status", "completed_at", "updated_at"])
            
            # Deactivate LiveKit room
            self._deactivate_livekit_room()
            
            # Create audit log entry (system action - no user)
            InterviewAuditLog.objects.create(
                interview_request=self,
                user=None,  # System action
                action=InterviewAuditLog.ACTION_COMPLETED,
                details={
                    'sender_joined_at': self.sender_joined_at.isoformat() if self.sender_joined_at else None,
                    'receiver_joined_at': self.receiver_joined_at.isoformat() if self.receiver_joined_at else None,
                    'auto_finalized': True,
                }
            )
        
        # Send notification (outside transaction)
        try:
            from apps.notifications.services import NotificationService
            NotificationService.notify_interview_completed(self, completed_by=None)
        except ImportError:
            pass  # Notifications app not installed
        
        return True


    @classmethod
    def has_active_request(cls, sender, receiver):
        qs = cls.objects.filter(
            sender=sender,
            receiver=receiver,
            status__in=cls.ACTIVE_STATUSES
        )

        for interview in qs:
            interview.finalize_if_expired()

        return cls.objects.filter(
            sender=sender,
            receiver=receiver,
            status__in=cls.ACTIVE_STATUSES
        ).exists()


    
    def select_time_option(self, time_option):
        """Select a specific time option and update scheduled_time."""
        if self.status != self.STATUS_PENDING:
            raise ValidationError(f"Cannot select time option for request with status '{self.status}'")
        
        if time_option.interview_request != self:
            raise ValidationError("Time option does not belong to this interview request")
        
        # Atomic update to prevent race conditions
        with transaction.atomic():
            # Clear any previously selected options
            self.time_options.update(is_selected=False)
            
            # Select the new option
            time_option.is_selected = True
            time_option.save(update_fields=['is_selected'])
            
            # Update scheduled_time to match selected option
            self.scheduled_time = time_option.proposed_time
            self.save(update_fields=['scheduled_time', 'updated_at'])
    
    def get_selected_time_option(self):
        """Get the currently selected time option."""
        try:
            return self.time_options.get(is_selected=True)
        except InterviewTimeOption.DoesNotExist:
            return None



class InterviewTimeOption(models.Model):
    """
    Time slot options for interview requests.
    
    Allows attenders to propose multiple time slots.
    Taker selects exactly one option during acceptance.
    """
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    interview_request = models.ForeignKey(
        InterviewRequest,
        related_name="time_options",
        on_delete=models.CASCADE,
        help_text='Interview request this time option belongs to'
    )
    
    proposed_time = models.DateTimeField(
        db_index=True,
        help_text='Proposed interview time'
    )
    
    is_selected = models.BooleanField(
        default=False,
        help_text='Whether this time option was selected by the taker'
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ["proposed_time"]
        unique_together = ("interview_request", "proposed_time")
        indexes = [
            models.Index(fields=['interview_request', 'is_selected']),
            models.Index(fields=['proposed_time']),
        ]
    
    def __str__(self):
        status = " (SELECTED)" if self.is_selected else ""
        return f"{self.interview_request} - {self.proposed_time}{status}"
    
    def clean(self):
        """Validate time option constraints."""
        # Proposed time must be in the future (for new options)
        if not self.pk and self.proposed_time:
            if self.proposed_time <= timezone.now():
                raise ValidationError("Proposed time must be in the future.")
    
    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class LiveKitRoom(models.Model):
    """
    LiveKit room model for interview sessions.
    
    Created lazily when an interview request is accepted.
    Room name format: interview-{uuid}
    
    Security:
    - Room is only created after acceptance
    - Tokens are short-lived and user-specific
    - Never expose API keys to frontend
    """
    
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False
    )
    
    # One-to-one relationship with interview request
    interview_request = models.OneToOneField(
        InterviewRequest,
        on_delete=models.CASCADE,
        related_name='livekit_room'
    )
    
    # Room name format: interview-{interview_request_uuid}
    room_name = models.CharField(
        max_length=100,
        unique=True,
        db_index=True,
        help_text='LiveKit room name (format: interview-{uuid})'
    )
    
    # Room creation and status tracking
    is_active = models.BooleanField(
        default=True,
        help_text='Whether the room is currently active'
    )
    
    # Participant tracking
    sender_joined_at = models.DateTimeField(null=True, blank=True)
    receiver_joined_at = models.DateTimeField(null=True, blank=True)
    
    # Audit timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        verbose_name = 'LiveKit Room'
        verbose_name_plural = 'LiveKit Rooms'
    
    def __str__(self):
        return f"Room: {self.room_name}"
    
    def mark_participant_joined(self, user):
        """Track when a participant joins the room."""
        #now = timezone.now()
        now = timezone.now().astimezone(timezone.UTC)
        if user == self.interview_request.sender:
            self.sender_joined_at = now
            self.save(update_fields=['sender_joined_at', 'updated_at'])
        elif user == self.interview_request.receiver:
            self.receiver_joined_at = now
            self.save(update_fields=['receiver_joined_at', 'updated_at'])
    
    def end_room(self):
        """Mark room as ended."""
        self.is_active = False
        self.ended_at = timezone.now()
        self.save(update_fields=['is_active', 'ended_at', 'updated_at'])


class InterviewAuditLog(models.Model):
    """
    Audit log for interview-related actions.
    
    Tracks all significant actions for security and compliance.
    """
    
    ACTION_CREATED = 'created'
    ACTION_ACCEPTED = 'accepted'
    ACTION_REJECTED = 'rejected'
    ACTION_CANCELLED = 'cancelled'
    ACTION_COMPLETED = 'completed'
    ACTION_NOT_ATTENDED = 'not_attended'
    ACTION_NOT_CONDUCTED = 'not_conducted'  # New: auto-expired
    ACTION_EXPIRED = 'expired'
    ACTION_JOINED = 'joined'
    ACTION_LEFT = 'left'
    ACTION_ADMIN_OVERRIDE = 'admin_override'
    
    ACTION_CHOICES = (
        (ACTION_CREATED, 'Created'),
        (ACTION_ACCEPTED, 'Accepted'),
        (ACTION_REJECTED, 'Rejected'),
        (ACTION_CANCELLED, 'Cancelled'),
        (ACTION_COMPLETED, 'Completed'),
        (ACTION_NOT_ATTENDED, 'Not Attended'),
        (ACTION_NOT_CONDUCTED, 'Not Conducted'),  # New: auto-expired
        (ACTION_EXPIRED, 'Expired'),
        (ACTION_JOINED, 'Joined Room'),
        (ACTION_LEFT, 'Left Room'),
        (ACTION_ADMIN_OVERRIDE, 'Admin Override'),
    )
    
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False
    )
    
    interview_request = models.ForeignKey(
        InterviewRequest,
        on_delete=models.CASCADE,
        related_name='audit_logs'
    )
    
    user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='interview_audit_logs'
    )
    
    action = models.CharField(
        max_length=20,
        choices=ACTION_CHOICES
    )
    
    details = models.JSONField(
        default=dict,
        blank=True,
        help_text='Additional action details'
    )
    
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True, default='')
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['interview_request', 'action']),
            models.Index(fields=['user', 'action']),
        ]
    
    def __str__(self):
        return f"{self.user} - {self.action} - {self.interview_request}"
    
    @classmethod
    def log_action(cls, interview_request, user, action, details=None, request=None):
        """Create an audit log entry."""
        ip_address = None
        user_agent = ''
        
        if request:
            ip_address = cls._get_client_ip(request)
            user_agent = request.META.get('HTTP_USER_AGENT', '')[:500]
        
        return cls.objects.create(
            interview_request=interview_request,
            user=user,
            action=action,
            details=details or {},
            ip_address=ip_address,
            user_agent=user_agent
        )
    
    @staticmethod
    def _get_client_ip(request):
        """Extract client IP from request."""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            return x_forwarded_for.split(',')[0].strip()
        return request.META.get('REMOTE_ADDR')
