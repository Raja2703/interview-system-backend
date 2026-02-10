# apps/interviews/views.py
"""
Interview Request API Views.

Provides:
- Interview request CRUD operations
- Multi-slot scheduling support
- LiveKit room management
- Role-based access control
"""

import logging
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, get_object_or_404
from django.db import transaction
from django.db import models
from rest_framework import status, generics, permissions
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.pagination import PageNumberPagination
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi

from apps.profiles.models import UserProfile
from .models import InterviewRequest, InterviewTimeOption, InterviewAuditLog
from .serializers import (
    InterviewRequestCreateSerializer,
    InterviewRequestSerializer,
    InterviewRequestListSerializer,
    InterviewRequestAcceptSerializer,
    InterviewRequestActionSerializer,
    LiveKitJoinSerializer,
)
from .permissions import (
    IsOnboardedAttender,
    IsOnboardedTaker,
    IsInterviewParticipant,
    IsInterviewReceiver,
    IsInterviewSender,
    CanJoinInterview,
    CanAcceptRejectInterview,
    CanCancelInterview,
)

logger = logging.getLogger(__name__)


class InterviewRequestCreateView(generics.CreateAPIView):
    """
    Create a new interview request with multiple time slot options.
    
    Attenders can propose 1-5 time slots for the interview.
    """
    serializer_class = InterviewRequestCreateSerializer
    permission_classes = [IsAuthenticated, IsOnboardedAttender]
    
    """def post(self, request, *args, **kwargs):
        response = super().create(request, *args, **kwargs)
        if response.status_code == status.HTTP_201_CREATED:
            # Return full serialized data
            interview_request = InterviewRequest.objects.get(uuid_id=response.data['id'])
            serializer = InterviewRequestSerializer(interview_request)
            response.data = serializer.data
        return response"""

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        interview_request = serializer.save()
        
        # Return full serialized data using the read serializer
        result_serializer = InterviewRequestSerializer(interview_request)
        return Response(result_serializer.data, status=status.HTTP_201_CREATED)    


class InterviewRequestListView(generics.ListAPIView):
    """
    List interview requests based on user role.
    
    - Attenders see requests they sent
    - Takers see requests they received
    """
    serializer_class = InterviewRequestListSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        user = self.request.user
        
        # Determine user role and filter accordingly
        if hasattr(user, 'profile'):
            profile = user.profile
            
            if profile.has_role('attender') and profile.has_role('taker'):
                # Both roles - show all interviews
                return InterviewRequest.objects.filter(
                    models.Q(sender=user) | models.Q(receiver=user)
                ).select_related('sender__profile', 'receiver__profile').order_by('-created_at')
            elif profile.has_role('attender'):
                # Attender only - show sent requests
                return InterviewRequest.objects.filter(
                    sender=user
                ).select_related('receiver__profile').order_by('-created_at')
            elif profile.has_role('taker'):
                # Taker only - show received requests
                return InterviewRequest.objects.filter(
                    receiver=user
                ).select_related('sender__profile').order_by('-created_at')
        
        return InterviewRequest.objects.none()


class InterviewRequestDetailView(generics.RetrieveAPIView):
    """
    Get detailed information about a specific interview request.
    
    Only participants (sender/receiver) can view details.
    """
    serializer_class = InterviewRequestSerializer
    permission_classes = [IsAuthenticated, IsInterviewParticipant]
    lookup_field = 'uuid_id'
    lookup_url_kwarg = 'interview_id'
    
    def get_queryset(self):
        return InterviewRequest.objects.select_related(
            'sender__profile', 'receiver__profile'
        ).prefetch_related('time_options')


class InterviewRequestAcceptView(APIView):
    """
    Accept an interview request by selecting one of the proposed time slots.
    
    Only the receiver (taker) can accept requests.
    
    Returns:
    - Full interview data with room metadata (room_name, livekit_url)
    - Does NOT return LiveKit token (use join endpoint)
    - join_endpoint indicates where to get the token
    """
    permission_classes = [IsAuthenticated, IsOnboardedTaker]
    
    def post(self, request, interview_id):
        interview_request = get_object_or_404(
            InterviewRequest.objects.select_related('sender__profile', 'receiver__profile')
                                   .prefetch_related('time_options'),
            uuid_id=interview_id
        )
        
        # Check permissions
        self.check_object_permissions(request, interview_request)
        
        # Additional permission check for acceptance
        if not CanAcceptRejectInterview().has_object_permission(request, self, interview_request):
            return Response(
                {'error': 'You cannot accept this interview request.'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        serializer = InterviewRequestAcceptSerializer(
            data=request.data,
            context={'interview_request': interview_request}
        )
        
        if serializer.is_valid():
            selected_time_option = serializer.validated_data['selected_time_option_id']
            
            with transaction.atomic():
                # Use select_for_update to prevent race conditions
                interview_request = InterviewRequest.objects.select_for_update().get(
                    uuid_id=interview_id
                )
                
                # Double-check status hasn't changed
                if interview_request.status != InterviewRequest.STATUS_PENDING:
                    return Response(
                        {'error': f'Interview request is no longer pending (status: {interview_request.status})'},
                        status=status.HTTP_400_BAD_REQUEST
                    )
                
                # Select the time option and accept the interview
                interview_request.select_time_option(selected_time_option)
                interview_request.accept()
                
                # Log the action
                InterviewAuditLog.log_action(
                    interview_request=interview_request,
                    user=request.user,
                    action=InterviewAuditLog.ACTION_ACCEPTED,
                    details={
                        'selected_time_option_id': str(selected_time_option.id),
                        'selected_time': selected_time_option.proposed_time.isoformat(),
                    },
                    request=request
                )
            
            # Refresh to get the LiveKit room
            interview_request.refresh_from_db()
            
            # Return updated interview data with room metadata
            output_serializer = InterviewRequestSerializer(interview_request)
            response_data = output_serializer.data
            
            # Add room metadata (but NOT the token)
            room = interview_request.get_livekit_room()
            if room:
                from django.conf import settings
                response_data['room_metadata'] = {
                    'room_name': room.room_name,
                    'livekit_url': getattr(settings, 'LIVEKIT_URL', None),
                    'join_endpoint': f'/api/interviews/{interview_id}/join/',
                    'note': 'Use join_endpoint to get your LiveKit access token when ready to join.'
                }
            
            return Response(response_data)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class InterviewRequestRejectView(APIView):
    """
    Reject an interview request.
    
    Only the receiver (taker) can reject requests.
    """
    permission_classes = [IsAuthenticated, IsOnboardedTaker]
    
    def post(self, request, interview_id):
        interview_request = get_object_or_404(
            InterviewRequest.objects.select_related('sender__profile', 'receiver__profile'),
            uuid_id=interview_id
        )
        
        # Check permissions
        if not CanAcceptRejectInterview().has_object_permission(request, self, interview_request):
            return Response(
                {'error': 'You cannot reject this interview request.'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        serializer = InterviewRequestActionSerializer(data=request.data)
        
        if serializer.is_valid():
            reason = serializer.validated_data.get('reason', '')
            
            with transaction.atomic():
                interview_request.reject(reason)
                
                # Log the action
                InterviewAuditLog.log_action(
                    interview_request=interview_request,
                    user=request.user,
                    action=InterviewAuditLog.ACTION_REJECTED,
                    details={'reason': reason},
                    request=request
                )
            
            serializer = InterviewRequestSerializer(interview_request)
            return Response(serializer.data)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class InterviewRequestCancelView(APIView):
    """
    Cancel an interview request.
    
    Only the sender (attender) can cancel requests.
    """
    permission_classes = [IsAuthenticated]
    
    def post(self, request, interview_id):
        interview_request = get_object_or_404(
            InterviewRequest.objects.select_related('sender__profile', 'receiver__profile'),
            uuid_id=interview_id
        )
        
        # Check permissions
        if not CanCancelInterview().has_object_permission(request, self, interview_request):
            return Response(
                {'error': 'You cannot cancel this interview request.'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        serializer = InterviewRequestActionSerializer(data=request.data)
        
        if serializer.is_valid():
            reason = serializer.validated_data.get('reason', '')
            
            with transaction.atomic():
                interview_request.cancel(reason)
                
                # Log the action
                InterviewAuditLog.log_action(
                    interview_request=interview_request,
                    user=request.user,
                    action=InterviewAuditLog.ACTION_CANCELLED,
                    details={'reason': reason},
                    request=request
                )
            
            serializer = InterviewRequestSerializer(interview_request)
            return Response(serializer.data)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# Legacy dashboard view (keeping for backward compatibility)
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def dashboard(request):
    """
    API endpoint for dashboard data.
    Returns user role and interview requests based on role.
    """
    logger.info(f"Dashboard accessed by user: {request.user.username}")

    try:
        profile = request.user.profile
    except UserProfile.DoesNotExist:
        logger.error(f"Profile not found for user: {request.user.username}")
        profile = UserProfile.objects.create(user=request.user)
        logger.info(f"Created missing profile for user: {request.user.username}")

    user_role = profile.role
    
    if not user_role:
        logger.info(f"User {request.user.username} has no role")
        return Response({
            "error": "No role assigned",
            "redirect_url": "/api/select-role/"
        }, status=403)

    if user_role == 'attender':
        interviews = InterviewRequest.objects.filter(sender=request.user)
        logger.info(f"User {request.user.username} (attender) has {interviews.count()} requests")
    elif user_role == 'taker':
        interviews = InterviewRequest.objects.filter(receiver=request.user)
        logger.info(f"User {request.user.username} (taker) has {interviews.count()} requests")
    else:
        logger.error(f"Invalid role for user {request.user.username}: {user_role}")
        return Response({"error": "Invalid role"}, status=400)

    interviews_data = [
        {
            "id": i.id,
            "sender": i.sender.username,
            "receiver": i.receiver.username,
            "status": i.status,
            "scheduled_time": i.scheduled_time.isoformat() if i.scheduled_time else None,
            "message": i.message,
            "created_at": i.created_at.isoformat(),
        }
        for i in interviews.order_by('-created_at')
    ]

    logger.info(f"Dashboard data returned for user: {request.user.username}")
    
    # Get user profile data for interview context
    profile_data = {
        "oauth_provider": profile.oauth_provider,
        "profile_picture": profile.profile_picture_url,
        "linkedin_profile": profile.linkedin_profile_url if profile.oauth_provider == 'linkedin' else None,
        "linkedin_id": profile.linkedin_id if profile.oauth_provider == 'linkedin' else None,
        "bio": profile.bio,
        "current_position": profile.current_position,
        "experience_years": profile.experience_years,
    }
    
    return Response({
        "role": user_role,
        "user": request.user.username,
        "email": request.user.email,
        "profile": profile_data,
        "interviews": interviews_data,
        "message": f"Welcome to your {user_role} dashboard! {'LinkedIn profile data available for interviews.' if profile.oauth_provider == 'linkedin' else ''}"
    })

