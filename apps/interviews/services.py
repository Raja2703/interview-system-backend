# apps/interviews/services.py
"""
Business logic services for interview management.

Provides:
- Interview request creation and management
- Time slot validation and selection
- LiveKit integration
- Audit logging
"""

from django.db import transaction
from django.utils import timezone
from .models import InterviewRequest, InterviewTimeOption, InterviewAuditLog
from django.db.models import Q
from .utils import validate_interview_time_slots, parse_datetime_input




class InterviewService:
    """Service class for interview-related business logic."""
    
    @staticmethod
    def create_interview_request(sender, receiver, time_slots, message="", topic="", duration_minutes=60):
        """
        Create an interview request with multiple time slot options.
        
        Args:
            sender: User sending the request (attender)
            receiver: User receiving the request (taker)
            time_slots: List of datetime strings or datetime objects
            message: Optional message to receiver
            topic: Optional interview topic
            duration_minutes: Interview duration in minutes
            
        Returns:
            InterviewRequest instance
            
        Raises:
            ValueError: If validation fails
            ValidationError: If constraints are violated (including insufficient credits)
        """
        # Validate time slots
        if isinstance(time_slots[0], str):
            parsed_times = validate_interview_time_slots(time_slots)
        else:
            parsed_times = time_slots
        
        # Check for existing active request
        if InterviewRequest.has_active_request(sender, receiver):
            raise ValueError("You already have an active interview request with this interviewer.")
        
        # Get credits from interviewer profile
        credits = 0
        try:
            interviewer_profile = receiver.profile.interviewer_profile
            credits = interviewer_profile.credits_per_interview
        except Exception:
            pass
        
        # Check if sender has sufficient credits (if credits are required)
        if credits > 0:
            try:
                from apps.credits.services import CreditService
                can_afford, balance, message_text = CreditService.check_can_request_interview(sender, credits)
                if not can_afford:
                    raise ValueError(f"Insufficient credits. Required: {credits}, Available: {balance}. Please add more credits to your account.")
            except ImportError:
                # Credits app not installed, skip check
                pass
        
        with transaction.atomic():
            # Create interview request with first time slot as default
            interview_request = InterviewRequest.objects.create(
                sender=sender,
                receiver=receiver,
                scheduled_time=parsed_times[0],
                message=message,
                topic=topic,
                duration_minutes=duration_minutes,
                credits=credits
            )
            
            # Create time options
            time_options = []
            for proposed_time in parsed_times:
                time_option = InterviewTimeOption(
                    interview_request=interview_request,
                    proposed_time=proposed_time
                )
                time_options.append(time_option)
            
            InterviewTimeOption.objects.bulk_create(time_options)
        
        return interview_request
    
    @staticmethod
    def accept_interview_request(interview_request, selected_time_option_id, user):
        """
        Accept an interview request by selecting a time slot.
        
        Args:
            interview_request: InterviewRequest instance
            selected_time_option_id: UUID of selected time option
            user: User accepting the request (must be receiver)
            
        Returns:
            Updated InterviewRequest instance
            
        Raises:
            PermissionError: If user is not the receiver
            ValueError: If request cannot be accepted or time option invalid
        """
        if interview_request.receiver != user:
            raise PermissionError("Only the receiver can accept this request.")
        
        if interview_request.status != InterviewRequest.STATUS_PENDING:
            raise ValueError(f"Cannot accept request with status '{interview_request.status}'")
        
        # Get the selected time option
        try:
            selected_time_option = interview_request.time_options.get(id=selected_time_option_id)
        except InterviewTimeOption.DoesNotExist:
            raise ValueError("Selected time option not found.")
        
        # Ensure the time is still in the future
        if selected_time_option.proposed_time <= timezone.now():
            raise ValueError("Selected time slot is in the past.")
        
        with transaction.atomic():
            # Use select_for_update to prevent race conditions
            interview_request = InterviewRequest.objects.select_for_update().get(
                id=interview_request.id
            )
            
            # Double-check status hasn't changed
            if interview_request.status != InterviewRequest.STATUS_PENDING:
                raise ValueError(f"Request status changed to '{interview_request.status}'")
            
            # Select the time option and accept
            interview_request.select_time_option(selected_time_option)
            interview_request.accept()
        
        return interview_request
    
    @staticmethod
    def reject_interview_request(interview_request, user, reason=""):
        """
        Reject an interview request.
        
        Args:
            interview_request: InterviewRequest instance
            user: User rejecting the request (must be receiver)
            reason: Optional rejection reason
            
        Returns:
            Updated InterviewRequest instance
            
        Raises:
            PermissionError: If user is not the receiver
            ValueError: If request cannot be rejected
        """
        if interview_request.receiver != user:
            raise PermissionError("Only the receiver can reject this request.")
        
        return interview_request.reject(reason)
    
    @staticmethod
    def cancel_interview_request(interview_request, user, reason=""):
        """
        Cancel an interview request.
        
        Args:
            interview_request: InterviewRequest instance
            user: User cancelling the request (must be sender or admin)
            reason: Optional cancellation reason
            
        Returns:
            Updated InterviewRequest instance
            
        Raises:
            PermissionError: If user cannot cancel this request
            ValueError: If request cannot be cancelled
        """
        is_admin = user.is_staff or user.is_superuser
        
        if not is_admin and interview_request.sender != user:
            raise PermissionError("Only the sender or admin can cancel this request.")
        
        return interview_request.cancel(reason)
    
    @staticmethod
    def complete_interview_request(interview_request, user):
        """
        Mark an interview request as completed.
        
        Args:
            interview_request: InterviewRequest instance
            user: User completing the request (participant or admin)
            
        Returns:
            Updated InterviewRequest instance
            
        Raises:
            PermissionError: If user cannot complete this request
            ValueError: If request cannot be completed
        """
        is_admin = user.is_staff or user.is_superuser
        is_participant = user in [interview_request.sender, interview_request.receiver]
        
        if not is_admin and not is_participant:
            raise PermissionError("Only participants or admin can complete this request.")
        
        return interview_request.complete()
    
    @staticmethod
    def get_user_interview_requests(user, status_filter=None):
        """
        Get interview requests for a user based on their role.
        
        Args:
            user: User instance
            status_filter: Optional status to filter by
            
        Returns:
            QuerySet of InterviewRequest instances
        """
        if not hasattr(user, 'profile'):
            return InterviewRequest.objects.none()
        
        profile = user.profile
        queryset = InterviewRequest.objects.none()
        
        if profile.has_role('attender') and profile.has_role('taker'):
            # Both roles - show all interviews
            queryset = InterviewRequest.objects.filter(
                Q(sender=user) | Q(receiver=user)
            )
        elif profile.has_role('attender'):
            # Attender only - show sent requests
            queryset = InterviewRequest.objects.filter(sender=user)
        elif profile.has_role('taker'):
            # Taker only - show received requests
            queryset = InterviewRequest.objects.filter(receiver=user)
        
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        
        return queryset.select_related(
            'sender__profile', 'receiver__profile'
        ).prefetch_related('time_options').order_by('-created_at')
    
    @staticmethod
    def can_create_interview_request(sender, receiver):
        """
        Check if a user can create an interview request with another user.
        
        Args:
            sender: User who wants to send the request
            receiver: User who would receive the request
            
        Returns:
            tuple: (can_create: bool, reason: str)
        """
        # Check if sender has attender role
        if not hasattr(sender, 'profile') or not sender.profile.has_role('attender'):
            return False, "Only interview attenders can send requests."
        
        # Check if receiver has taker role
        if not hasattr(receiver, 'profile') or not receiver.profile.has_role('taker'):
            return False, "Selected user is not an interviewer."
        
        # Check if receiver has completed onboarding
        if not receiver.profile.onboarding_completed:
            return False, "Selected interviewer has not completed their profile setup."
        
        # Check sender != receiver
        if sender == receiver:
            return False, "You cannot send an interview request to yourself."
        
        # Check for existing active request
        if InterviewRequest.has_active_request(sender, receiver):
            return False, "You already have an active interview request with this interviewer."
        
        # Check if sender has sufficient credits
        try:
            credits_required = 0
            try:
                interviewer_profile = receiver.profile.interviewer_profile
                credits_required = interviewer_profile.credits_per_interview
            except Exception:
                pass
            
            if credits_required > 0:
                from apps.credits.services import CreditService
                can_afford, balance, _ = CreditService.check_can_request_interview(sender, credits_required)
                if not can_afford:
                    return False, f"Insufficient credits. Required: {credits_required}, Available: {balance}."
        except ImportError:
            # Credits app not installed, skip check
            pass
        
        return True, "Can create interview request."

