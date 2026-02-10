# apps/interviews/serializers.py
"""
Serializers for Interview Request and LiveKit Room models.

Includes:
- InterviewRequestCreateSerializer: For creating new interview requests with multiple time slots
- InterviewRequestSerializer: Full read serializer with nested data
- InterviewRequestListSerializer: Compact list serializer
- InterviewTimeOptionSerializer: For time slot management
- LiveKitJoinSerializer: For join room responses
- Admin serializers for interview management
"""
from rest_framework import serializers
from django.utils import timezone
from django.db import transaction
from .models import InterviewRequest, InterviewTimeOption, LiveKitRoom, InterviewAuditLog
from .utils import parse_datetime_input, validate_interview_time_slots, format_datetime_ist_for_serializer
import datetime
from .feedback_models import FeedbackStatus,InterviewerFeedback 

class ISTDateTimeField(serializers.DateTimeField):
    """
    Custom DateTimeField that converts UTC datetimes to IST for output.
    
    This ensures API responses always show times in IST (+05:30) 
    regardless of server timezone, while keeping database storage in UTC.
    """
    
    def to_representation(self, value):
        if value is None:
            return None
        # Convert to IST before serialization
        ist_value = format_datetime_ist_for_serializer(value)
        return super().to_representation(ist_value)


class InterviewTimeOptionSerializer(serializers.ModelSerializer):
    """Serializer for interview time options."""
    
    id = serializers.UUIDField(read_only=True)
    proposed_time = ISTDateTimeField(read_only=True)
    is_selected = serializers.BooleanField(read_only=True)
    created_at = ISTDateTimeField(read_only=True)
    
    class Meta:
        model = InterviewTimeOption
        fields = ['id', 'proposed_time', 'is_selected', 'created_at']
        read_only_fields = fields


class InterviewRequestCreateSerializer(serializers.ModelSerializer):
    """
    Serializer for creating new interview requests with multiple time slots.
    
    Required fields:
    - receiver_id: UUID of the interviewer (taker)
    - time_slots: List of proposed datetime strings (1-5 slots)
    
    Optional fields:
    - message: Message to the interviewer
    - topic: Interview topic/focus
    - duration_minutes: Interview duration (default: 60)
    """
    
    receiver_id = serializers.UUIDField(
        write_only=True,
        help_text='UUID (public_id) of the interviewer to send request to'
    )
    
    time_slots = serializers.ListField(
        child=serializers.CharField(),
        write_only=True,
        min_length=1,
        max_length=5,
        help_text='List of proposed datetime strings (1-5 slots). Supports ISO 8601 and human-friendly formats.'
    )
    
    # Remove scheduled_time from create serializer since we use time_slots
    class Meta:
        model = InterviewRequest
        fields = [
            'receiver_id',
            'time_slots',
            'message',
            'topic',
            'duration_minutes',
        ]
        extra_kwargs = {
            'message': {'required': False, 'allow_blank': True},
            'topic': {'required': False, 'allow_blank': True},
            'duration_minutes': {'required': False, 'default': 60},
        }
    
    def validate_time_slots(self, value):
        """Validate and parse time slots."""
        try:
            return validate_interview_time_slots(value)
        except ValueError as e:
            raise serializers.ValidationError(str(e))
    
    def validate_duration_minutes(self, value):
        """Validate duration is reasonable."""
        if value < 15:
            raise serializers.ValidationError("Interview duration must be at least 15 minutes.")
        if value > 240:
            raise serializers.ValidationError("Interview duration cannot exceed 4 hours (240 minutes).")
        return value
    
    def validate_receiver_id(self, value):
        """Validate receiver exists and is an interviewer (taker)."""
        from apps.profiles.models import UserProfile
        
        try:
            profile = UserProfile.objects.select_related('user').get(public_id=value)
        except UserProfile.DoesNotExist:
            raise serializers.ValidationError("User not found.")
        
        # Check if receiver has taker role
        if not profile.has_role('taker'):
            raise serializers.ValidationError("Selected user is not an interviewer.")
        
        # Check if receiver has completed onboarding
        if not profile.onboarding_completed:
            raise serializers.ValidationError("Selected interviewer has not completed their profile setup.")
        
        return profile.user
    
    def validate(self, attrs):
        """Additional validation for the entire request."""
        request = self.context.get('request')
        sender = request.user if request else None
        receiver = attrs.get('receiver_id')  # This is now the User object
        
        if not sender:
            raise serializers.ValidationError("Authentication required.")
        
        # Check sender has attender role
        if hasattr(sender, 'profile') and not sender.profile.has_role('attender'):
            raise serializers.ValidationError({
                'sender': "Only interview attenders can send interview requests."
            })
        
        # Check sender != receiver
        if sender == receiver:
            raise serializers.ValidationError({
                'receiver_id': "You cannot send an interview request to yourself."
            })
        
        # Check for existing active request
        if InterviewRequest.has_active_request(sender, receiver):
            raise serializers.ValidationError({
                'receiver_id': "You already have an active or pending interview request with this interviewer."
            })
        
        # Store validated receiver for create
        attrs['receiver'] = receiver
        del attrs['receiver_id']
        
        return attrs
    
    def create(self, validated_data):
        """Create interview request with multiple time options."""
        request = self.context.get('request')
        sender = request.user
        time_slots = validated_data.pop('time_slots')
        
        # Get credits from interviewer profile
        receiver = validated_data['receiver']
        credits = 0
        try:
            interviewer_profile = receiver.profile.interviewer_profile
            credits = interviewer_profile.credits_per_interview
        except Exception:
            pass
        
        validated_data['sender'] = sender
        validated_data['credits'] = credits
        
        # Set scheduled_time to first time slot (will be updated when taker selects)
        validated_data['scheduled_time'] = time_slots[0]
        
        with transaction.atomic():
            # Create interview request
            interview_request = InterviewRequest.objects.create(**validated_data)
            
            # Create time options
            time_options = []
            for proposed_time in time_slots:
                time_option = InterviewTimeOption(
                    interview_request=interview_request,
                    proposed_time=proposed_time
                )
                time_options.append(time_option)
            
            InterviewTimeOption.objects.bulk_create(time_options)
            
            # Log the action
            InterviewAuditLog.log_action(
                interview_request=interview_request,
                user=sender,
                action=InterviewAuditLog.ACTION_CREATED,
                details={
                    'receiver_id': str(receiver.profile.public_id),
                    'time_slots': [t.isoformat() for t in time_slots],
                    'time_slots_count': len(time_slots),
                },
                request=request
            )
        
        return interview_request


class InterviewRequestAcceptSerializer(serializers.Serializer):
    """Serializer for accepting interview requests with time slot selection."""
    
    selected_time_option_id = serializers.UUIDField(
        help_text='UUID of the selected time option'
    )
    
    def validate_selected_time_option_id(self, value):
        """Validate the selected time option exists and belongs to this interview."""
        interview_request = self.context.get('interview_request')
        
        if not interview_request:
            raise serializers.ValidationError("Interview request context required.")
        
        try:
            time_option = interview_request.time_options.get(id=value)
        except InterviewTimeOption.DoesNotExist:
            raise serializers.ValidationError("Selected time option not found.")
        
        # Ensure the time is still in the future
        if time_option.proposed_time <= timezone.now():
            raise serializers.ValidationError("Selected time slot is in the past.")
        
        return time_option


class ParticipantSerializer(serializers.Serializer):
    """Lightweight serializer for interview participants."""
    id = serializers.UUIDField(source='profile.public_id', read_only=True)
    username = serializers.CharField(read_only=True)
    name = serializers.CharField(source='profile.name', read_only=True)
    profile_picture_url = serializers.URLField(source='profile.profile_picture_url', read_only=True)
    designation = serializers.CharField(source='profile.designation', read_only=True)
    company = serializers.CharField(source='profile.company', read_only=True)


class InterviewRequestSerializer(serializers.ModelSerializer):
    """
    Full read serializer for InterviewRequest.
    
    Includes nested sender and receiver data, and time options.
    All datetime fields are output in IST (+05:30) for user convenience.
    """
    # Expose uuid_id as 'id' for API responses
    id = serializers.UUIDField(source='uuid_id', read_only=True)
    sender = ParticipantSerializer(read_only=True)
    receiver = ParticipantSerializer(read_only=True)
    time_options = InterviewTimeOptionSerializer(many=True, read_only=True)
    selected_time_option = serializers.SerializerMethodField()
    is_joinable = serializers.SerializerMethodField()
    time_until_start = serializers.SerializerMethodField()
    has_room = serializers.SerializerMethodField()
    
    # Override datetime fields to use IST for output
    scheduled_time = ISTDateTimeField(read_only=True)
    created_at = ISTDateTimeField(read_only=True)
    updated_at = ISTDateTimeField(read_only=True)
    accepted_at = ISTDateTimeField(read_only=True)
    rejected_at = ISTDateTimeField(read_only=True)
    cancelled_at = ISTDateTimeField(read_only=True)
    completed_at = ISTDateTimeField(read_only=True)
    expired_at = ISTDateTimeField(read_only=True)
    # Attendance tracking
    sender_joined_at = ISTDateTimeField(read_only=True)
    receiver_joined_at = ISTDateTimeField(read_only=True)
    
    class Meta:
        model = InterviewRequest
        fields = [
            'id',  # This is uuid_id
            'sender',
            'receiver',
            'scheduled_time',
            'duration_minutes',
            'message',
            'topic',
            'status',
            'rejection_reason',
            'credits',
            'time_options',
            'selected_time_option',
            'is_joinable',
            'time_until_start',
            'has_room',
            'created_at',
            'updated_at',
            'accepted_at',
            'rejected_at',
            'cancelled_at',
            'completed_at',
            'expired_at',
            'sender_joined_at',
            'receiver_joined_at',
        ]
        read_only_fields = fields
    
    def get_selected_time_option(self, obj):
        """Get the selected time option if any."""
        selected = obj.get_selected_time_option()
        if selected:
            return InterviewTimeOptionSerializer(selected).data
        return None
    
    def get_is_joinable(self, obj):
        """Check if interview can be joined now."""
        return obj.is_joinable()
    
    def get_time_until_start(self, obj):
        """Get time until interview start in minutes."""
        if obj.status != InterviewRequest.STATUS_ACCEPTED:
            return None
        now_utc = timezone.now().astimezone(datetime.timezone.utc)
        delta = obj.scheduled_time.astimezone(datetime.timezone.utc) - now_utc
        minutes = int(delta.total_seconds() / 60)
        return minutes if minutes > 0 else 0
    
    def get_has_room(self, obj):
        """Check if LiveKit room exists."""
        try:
            return hasattr(obj, 'livekit_room') and obj.livekit_room is not None
        except Exception:
            return False


class InterviewRequestListSerializer(serializers.ModelSerializer):
    """
    Compact serializer for listing interview requests.
    All datetime fields are output in IST (+05:30).
    """
    # Expose uuid_id as 'id' for API responses
    id = serializers.UUIDField(source='uuid_id', read_only=True)
    sender_id = serializers.UUIDField(source='sender.profile.public_id', read_only=True)
    sender_name = serializers.CharField(source='sender.profile.name', read_only=True)
    receiver_id = serializers.UUIDField(source='receiver.profile.public_id', read_only=True)
    receiver_name = serializers.CharField(source='receiver.profile.name', read_only=True)
    is_joinable = serializers.SerializerMethodField()
    
    # Override datetime fields to use IST for output
    scheduled_time = ISTDateTimeField(read_only=True)
    created_at = ISTDateTimeField(read_only=True)
    
    has_pending_feedback = serializers.SerializerMethodField()

    def get_has_pending_feedback(self, obj):
        if not hasattr(obj, "interviewer_feedback"):
            return True
        return obj.interviewer_feedback.status == FeedbackStatus.PENDING
    class Meta:
        model = InterviewRequest
        fields = [
            'id',  # This is uuid_id
            'sender_id',
            'sender_name',
            'receiver_id',
            'receiver_name',
            'scheduled_time',
            'duration_minutes',
            'topic',
            'status',
            'credits',
            'is_joinable',
            'created_at',
            'has_pending_feedback',
        ]
        read_only_fields = fields
    
    def get_is_joinable(self, obj):
        return obj.is_joinable()


class InterviewRequestActionSerializer(serializers.Serializer):
    """Serializer for interview request actions (accept/reject/cancel)."""
    reason = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=500,
        help_text='Optional reason for rejection or cancellation'
    )


class LiveKitJoinSerializer(serializers.Serializer):
    """Serializer for LiveKit join response."""
    token = serializers.CharField(read_only=True)
    room_name = serializers.CharField(read_only=True)
    livekit_url = serializers.CharField(read_only=True)
    identity = serializers.CharField(read_only=True)
    expires_at = serializers.CharField(read_only=True)
    permissions = serializers.DictField(read_only=True)
    interview = InterviewRequestSerializer(read_only=True)


class InterviewAuditLogSerializer(serializers.ModelSerializer):
    """Serializer for interview audit logs. Datetime in IST (+05:30)."""
    user_id = serializers.UUIDField(source='user.profile.public_id', read_only=True)
    user_email = serializers.EmailField(source='user.email', read_only=True)
    created_at = ISTDateTimeField(read_only=True)
    
    class Meta:
        model = InterviewAuditLog
        fields = [
            'id',
            'interview_request_id',
            'user_id',
            'user_email',
            'action',
            'details',
            'ip_address',
            'created_at',
        ]
        read_only_fields = fields


# ========== ADMIN SERIALIZERS ==========


class AdminInterviewRequestSerializer(serializers.ModelSerializer):
    """
    Full admin serializer for InterviewRequest.
    
    Includes all fields and audit information.
    All datetime fields are output in IST (+05:30).
    """
    sender = ParticipantSerializer(read_only=True)
    receiver = ParticipantSerializer(read_only=True)
    audit_logs = InterviewAuditLogSerializer(many=True, read_only=True)
    livekit_room = serializers.SerializerMethodField()
    
    # Override datetime fields to use IST for output
    scheduled_time = ISTDateTimeField(read_only=True)
    created_at = ISTDateTimeField(read_only=True)
    updated_at = ISTDateTimeField(read_only=True)
    accepted_at = ISTDateTimeField(read_only=True)
    rejected_at = ISTDateTimeField(read_only=True)
    cancelled_at = ISTDateTimeField(read_only=True)
    completed_at = ISTDateTimeField(read_only=True)
    expired_at = ISTDateTimeField(read_only=True)
    # Attendance tracking from InterviewRequest model
    sender_joined_at = ISTDateTimeField(read_only=True)
    receiver_joined_at = ISTDateTimeField(read_only=True)
    
    class Meta:
        model = InterviewRequest
        fields = [
            'id',
            'sender',
            'receiver',
            'scheduled_time',
            'duration_minutes',
            'message',
            'topic',
            'status',
            'rejection_reason',
            'credits',
            'created_at',
            'updated_at',
            'accepted_at',
            'rejected_at',
            'cancelled_at',
            'completed_at',
            'expired_at',
            'sender_joined_at',
            'receiver_joined_at',
            'livekit_room',
            'audit_logs',
        ]
        read_only_fields = fields
    
    def get_livekit_room(self, obj):
        try:
            room = obj.livekit_room
            return {
                'room_name': room.room_name,
                'is_active': room.is_active,
                'sender_joined_at': format_datetime_ist_for_serializer(room.sender_joined_at).isoformat() if room.sender_joined_at else None,
                'receiver_joined_at': format_datetime_ist_for_serializer(room.receiver_joined_at).isoformat() if room.receiver_joined_at else None,
                'created_at': format_datetime_ist_for_serializer(room.created_at).isoformat() if room.created_at else None,
                'ended_at': format_datetime_ist_for_serializer(room.ended_at).isoformat() if room.ended_at else None,
            }
        except Exception:
            return None


class AdminInterviewActionSerializer(serializers.Serializer):
    """Serializer for admin interview actions."""
    action = serializers.ChoiceField(
        choices=['cancel', 'complete'],
        help_text='Action to perform: cancel or complete'
    )
    reason = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=500,
        help_text='Reason for the action'
    )
