# apps/interviews/api.py
"""
Interview Request API endpoints.

Endpoints:
1) POST /api/interviews/requests/ - Create interview request
2) GET  /api/interviews/requests/ - List interview requests
3) GET  /api/interviews/requests/{id}/ - Get interview request details
4) POST /api/interviews/requests/{id}/accept/ - Accept interview request
5) POST /api/interviews/requests/{id}/reject/ - Reject interview request
6) POST /api/interviews/requests/{id}/cancel/ - Cancel interview request
7) POST /api/interviews/{id}/join/ - Join interview room (get LiveKit token)

Admin Endpoints:
8) GET  /api/admin/interviews/ - List all interviews (admin only)
9) GET  /api/admin/interviews/{id}/ - Get interview details (admin only)
10) POST /api/admin/interviews/{id}/action/ - Admin actions on interview

Interview Status Flow:
- pending → accepted (taker accepts) | rejected (taker rejects) | cancelled (sender/admin cancels)
- accepted → completed (both attended) | not_attended (taker manual mark) | not_conducted (auto-expiry) | cancelled
- Terminal states: completed, rejected, cancelled, not_attended, not_conducted

Auto-Expiry Logic (20-minute rule):
- If NEITHER participant joins within 20 minutes of scheduled_time → not_conducted
- If ONLY ONE participant joins and 20 minutes pass → not_conducted
- If BOTH participants joined → completed (when time window ends)

Attendance Tracking:
- sender_joined_at: When the attender joined the interview room
- receiver_joined_at: When the taker (interviewer) joined the interview room

Security:
- All endpoints require authentication
- Role-based permissions enforced
- Audit logging for all actions
- Rate limiting hooks available
"""
import logging
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404
from django.db.models import Q
from django.utils import timezone
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi
from .feedback_models import FeedbackStatus, InterviewerFeedback
from .models import InterviewRequest, InterviewAuditLog
from .serializers import (
    InterviewRequestSerializer,
    InterviewRequestListSerializer,
    InterviewRequestCreateSerializer,
    InterviewRequestActionSerializer,
    InterviewRequestAcceptSerializer,
    LiveKitJoinSerializer,
    AdminInterviewRequestSerializer,
    AdminInterviewActionSerializer,
)
from .permissions import (
    IsAttender,
    IsTaker,
    IsOnboardedAttender,
    OnboardingCompleted,
    IsAdmin,
    IsInterviewParticipant,
    CanJoinInterview,
    CanAcceptRejectInterview,
    CanCancelInterview,
)
from .services.livekit import get_livekit_service

logger = logging.getLogger(__name__)


# ========== INTERVIEW REQUEST APIS ==========


class InterviewRequestCreateAPI(generics.CreateAPIView):
    """
    Create a new interview request.

    POST /api/interviews/requests/

    Requirements:
    - User must be authenticated
    - User must have 'attender' role
    - User must have completed onboarding

    Request Body:
    - receiver_id: UUID of the interviewer
    - scheduled_time: ISO datetime for the interview
    - message: Optional message to the interviewer
    - topic: Optional interview topic
    - duration_minutes: Optional duration (default: 60)
    """

    serializer_class = InterviewRequestCreateSerializer
    permission_classes = [IsAuthenticated, IsOnboardedAttender]

    @swagger_auto_schema(
        tags=["Interviews"],
        operation_summary="Create Interview Request",
        operation_description="Send a new interview request to an interviewer (taker).",
        responses={
            201: InterviewRequestSerializer,
            400: "Validation error",
            403: "Permission denied - must be an attender with completed onboarding",
        },
    )
    def post(self, request, *args, **kwargs):
        return super().post(request, *args, **kwargs)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        interview_request = serializer.save()

        # Return full serialized data
        output_serializer = InterviewRequestSerializer(interview_request)

        logger.info(
            f"Interview request created: {interview_request.id} "
            f"(sender: {request.user.email}, receiver: {interview_request.receiver.email})"
        )

        # Send notification to receiver
        try:
            from apps.notifications.services import NotificationService

            NotificationService.notify_interview_created(interview_request)
        except ImportError:
            pass  # Notifications app not installed

        return Response(output_serializer.data, status=status.HTTP_201_CREATED)


class InterviewRequestListAPI(generics.ListAPIView):
    """
    List interview requests for the current user.

    GET /api/interviews/requests/

    Query Parameters:
    - type: 'sent' | 'received' | 'all' (default: 'all')
    - status: Filter by status (pending, accepted, rejected, cancelled, completed, expired)

    Returns:
    - Sent requests if user is attender
    - Received requests if user is taker
    - Both if user has both roles
    """

    serializer_class = InterviewRequestListSerializer
    permission_classes = [IsAuthenticated, OnboardingCompleted]

    @swagger_auto_schema(
        tags=["Interviews"],
        operation_summary="List Interview Requests",
        operation_description="Get list of interview requests for the current user.",
        manual_parameters=[
            openapi.Parameter(
                "type",
                openapi.IN_QUERY,
                type=openapi.TYPE_STRING,
                enum=["sent", "received", "all"],
                description="Filter by request type",
            ),
            openapi.Parameter(
                "status",
                openapi.IN_QUERY,
                type=openapi.TYPE_STRING,
                enum=[
                    "pending",
                    "accepted",
                    "rejected",
                    "cancelled",
                    "completed",
                    "not attended",
                ],
                description="Filter by status (including 'not attended')",
            ),
        ],
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        user = self.request.user
        request_type = self.request.query_params.get("type", "all")
        status_filter = self.request.query_params.get("status")

        # Build base queryset based on type
        if request_type == "sent":
            queryset = InterviewRequest.objects.filter(sender=user)
        elif request_type == "received":
            queryset = InterviewRequest.objects.filter(receiver=user)
        else:  # 'all'
            queryset = InterviewRequest.objects.filter(
                Q(sender=user) | Q(receiver=user)
            )

        # Apply status filter if provided
        if status_filter:
            queryset = queryset.filter(status=status_filter)

        return queryset.select_related(
            "sender", "sender__profile", "receiver", "receiver__profile"
        ).order_by("-created_at")


class InterviewRequestDetailAPI(generics.RetrieveAPIView):
    """
    Get interview request details.

    GET /api/interviews/requests/{id}/

    Requirements:
    - User must be a participant (sender or receiver)
    """

    serializer_class = InterviewRequestSerializer
    permission_classes = [IsAuthenticated, IsInterviewParticipant]
    lookup_field = "uuid_id"
    lookup_url_kwarg = "id"  # URL uses 'id' but we look up by 'uuid_id'

    def get_queryset(self):
        return InterviewRequest.objects.select_related(
            "sender", "sender__profile", "receiver", "receiver__profile"
        )

    @swagger_auto_schema(
        tags=["Interviews"],
        operation_summary="Get Interview Request Details",
        operation_description="Get detailed information about an interview request.",
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)


class InterviewRequestAcceptAPI(APIView):
    """
    Accept an interview request.

    POST /api/interviews/requests/{id}/accept/

    Requirements:
    - User must be the receiver (interviewer/taker)
    - Interview must be in 'pending' status

    Effects:
    - Status changes to 'accepted'
    - LiveKit room is created
    - Audit log entry created
    """

    permission_classes = [IsAuthenticated, IsTaker]

    @swagger_auto_schema(
        tags=["Interviews"],
        operation_summary="Accept Interview Request",
        operation_description="Accept a pending interview request. Requires selecting a time slot.",
        request_body=InterviewRequestAcceptSerializer,
        responses={
            200: InterviewRequestSerializer,
            400: "Invalid status transition or invalid time slot",
            403: "Permission denied - only receiver can accept",
            404: "Interview request not found",
        },
    )
    def post(self, request, id):
        interview = get_object_or_404(
            InterviewRequest.objects.select_related(
                "sender", "sender__profile", "receiver", "receiver__profile"
            ),
            uuid_id=id,
        )

        # Check permissions
        permission = CanAcceptRejectInterview()
        if not permission.has_object_permission(request, self, interview):
            return Response(
                {"error": permission.message}, status=status.HTTP_403_FORBIDDEN
            )

        # Validate input (time slot selection)
        serializer = InterviewRequestAcceptSerializer(
            data=request.data, context={"interview_request": interview}
        )

        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        # Get the validate time_option object (returned by validate_selected_time_option_id)
        time_option = serializer.validated_data["selected_time_option_id"]

        try:
            # Select time option first
            interview.select_time_option(time_option)

            # Then accept
            interview.accept()

            # Log action
            InterviewAuditLog.log_action(
                interview_request=interview,
                user=request.user,
                action=InterviewAuditLog.ACTION_ACCEPTED,
                details={
                    "selected_time_id": str(time_option.id),
                    "scheduled_time": time_option.proposed_time.isoformat(),
                },
                request=request,
            )

            logger.info(
                f"Interview request {id} accepted by {request.user.email} for {time_option.proposed_time}"
            )

            # Send notification to sender
            try:
                from apps.notifications.services import NotificationService

                NotificationService.notify_interview_accepted(interview)
            except ImportError:
                pass  # Notifications app not installed

            response_serializer = InterviewRequestSerializer(interview)
            return Response(response_serializer.data)

        except Exception as e:
            logger.error(f"Error accepting interview {id}: {str(e)}")
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


class InterviewRequestRejectAPI(APIView):
    """
    Reject an interview request.

    POST /api/interviews/requests/{id}/reject/

    Requirements:
    - User must be the receiver (interviewer/taker)
    - Interview must be in 'pending' status

    Request Body (optional):
    - reason: Rejection reason
    """

    permission_classes = [IsAuthenticated, IsTaker]

    @swagger_auto_schema(
        tags=["Interviews"],
        operation_summary="Reject Interview Request",
        operation_description="Reject a pending interview request.",
        request_body=InterviewRequestActionSerializer,
        responses={
            200: InterviewRequestSerializer,
            400: "Invalid status transition",
            403: "Permission denied - only receiver can reject",
            404: "Interview request not found",
        },
    )
    def post(self, request, id):
        interview = get_object_or_404(
            InterviewRequest.objects.select_related(
                "sender", "sender__profile", "receiver", "receiver__profile"
            ),
            uuid_id=id,  # Look up by uuid_id
        )

        # Check permissions
        permission = CanAcceptRejectInterview()
        if not permission.has_object_permission(request, self, interview):
            return Response(
                {"error": permission.message}, status=status.HTTP_403_FORBIDDEN
            )

        # Get reason from request
        serializer = InterviewRequestActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        reason = serializer.validated_data.get("reason", "")

        try:
            interview.reject(reason=reason)

            # Log action
            InterviewAuditLog.log_action(
                interview_request=interview,
                user=request.user,
                action=InterviewAuditLog.ACTION_REJECTED,
                details={"reason": reason},
                request=request,
            )

            logger.info(f"Interview request {id} rejected by {request.user.email}")

            # Send notification to sender
            try:
                from apps.notifications.services import NotificationService

                NotificationService.notify_interview_rejected(interview)
            except ImportError:
                pass  # Notifications app not installed

            output_serializer = InterviewRequestSerializer(interview)
            return Response(output_serializer.data)

        except Exception as e:
            logger.error(f"Error rejecting interview {id}: {str(e)}")
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


class InterviewRequestCancelAPI(APIView):
    """
    Cancel an interview request.

    POST /api/interviews/requests/{id}/cancel/

    Requirements:
    - User must be the sender (attender) OR admin
    - Interview must be in 'pending' or 'accepted' status

    Request Body (optional):
    - reason: Cancellation reason
    """

    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        tags=["Interviews"],
        operation_summary="Cancel Interview Request",
        operation_description="Cancel a pending or accepted interview request.",
        request_body=InterviewRequestActionSerializer,
        responses={
            200: InterviewRequestSerializer,
            400: "Invalid status transition",
            403: "Permission denied - only sender can cancel",
            404: "Interview request not found",
        },
    )
    def post(self, request, id):
        interview = get_object_or_404(
            InterviewRequest.objects.select_related(
                "sender", "sender__profile", "receiver", "receiver__profile"
            ),
            uuid_id=id,  # Look up by uuid_id
        )

        # Check permissions
        permission = CanCancelInterview()
        if not permission.has_object_permission(request, self, interview):
            return Response(
                {"error": permission.message}, status=status.HTTP_403_FORBIDDEN
            )

        # Get reason from request
        serializer = InterviewRequestActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        reason = serializer.validated_data.get("reason", "")

        try:
            interview.cancel(reason=reason)

            # Log action
            InterviewAuditLog.log_action(
                interview_request=interview,
                user=request.user,
                action=InterviewAuditLog.ACTION_CANCELLED,
                details={"reason": reason},
                request=request,
            )

            logger.info(f"Interview request {id} cancelled by {request.user.email}")

            # Send notification to the other participant
            try:
                from apps.notifications.services import NotificationService

                NotificationService.notify_interview_cancelled(
                    interview, cancelled_by=request.user
                )
            except ImportError:
                pass  # Notifications app not installed

            output_serializer = InterviewRequestSerializer(interview)
            return Response(output_serializer.data)

        except Exception as e:
            logger.error(f"Error cancelling interview {id}: {str(e)}")
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


class InterviewJoinAPI(APIView):
    """
    Join an interview room (get LiveKit token).

    POST /api/interviews/{id}/join/

    Requirements:
    - User must be a participant (sender or receiver)
    - Interview must be accepted
    - Must be within joinable time window (15 min before to end of duration + 30 min)
    - Admins CANNOT join rooms

    Returns:
    - LiveKit token
    - Room name
    - LiveKit server URL
    - User identity
    - Expiration time
    - Permissions (can_publish, can_subscribe, etc.)
    """

    permission_classes = [IsAuthenticated, CanJoinInterview]

    @swagger_auto_schema(
        tags=["Interviews"],
        operation_summary="Join Interview Room",
        operation_description="""
Get LiveKit token to join the interview video room.

**Attendance Tracking:**
When a participant joins, their join timestamp is recorded:
- `sender_joined_at`: Updated when the attender joins
- `receiver_joined_at`: Updated when the interviewer joins

**Status Requirements:**
- Interview must be in 'accepted' status
- Cannot join if status is: completed, not_conducted, not_attended, cancelled, rejected, pending

**Time Window:**
- Opens 15 minutes before scheduled_time
- Closes at scheduled_time + duration + 30 minutes
        """,
        responses={
            200: LiveKitJoinSerializer,
            400: "Cannot join - invalid state or time window",
            403: "Permission denied",
            404: "Interview not found",
            503: "LiveKit service unavailable",
        },
    )
    def post(self, request, id):
        interview = get_object_or_404(
            InterviewRequest.objects.select_related(
                "sender", "sender__profile", "receiver", "receiver__profile"
            ),
            uuid_id=id,  # Look up by uuid_id
        )

        # Object permissions are checked by CanJoinInterview
        self.check_object_permissions(request, interview)

        # Get LiveKit service
        livekit = get_livekit_service()

        # Validate and create token
        is_valid, error = livekit.validate_join_request(interview, request.user)
        if not is_valid:
            return Response({"error": error}, status=status.HTTP_400_BAD_REQUEST)

        try:
            token_data = livekit.create_access_token(
                interview_request=interview, user=request.user
            )

            # Track attendance on InterviewRequest model directly
            # This is used by the finalize_if_expired task for 20-min expiry logic
            now = timezone.now()
            if request.user == interview.sender:
                if not interview.sender_joined_at:
                    interview.sender_joined_at = now
                    interview.save(update_fields=["sender_joined_at", "updated_at"])
            elif request.user == interview.receiver:
                if not interview.receiver_joined_at:
                    interview.receiver_joined_at = now
                    interview.save(update_fields=["receiver_joined_at", "updated_at"])

            # Also mark on LiveKitRoom for backward compatibility
            room = interview.get_livekit_room()
            if room:
                room.mark_participant_joined(request.user)

            # Log action with structured logging
            InterviewAuditLog.log_action(
                interview_request=interview,
                user=request.user,
                action=InterviewAuditLog.ACTION_JOINED,
                details={
                    "room_name": token_data["room_name"],
                    "identity": token_data["identity"],
                },
                request=request,
            )

            logger.info(
                f"[INTERVIEW_JOIN] interview={interview.uuid_id} "
                f"user={request.user.email} room={token_data['room_name']}"
            )

            is_interviewer = request.user == interview.receiver

            # Add interview data to response
            interview_serializer = InterviewRequestSerializer(interview)
            response_data = {
                **token_data,
                "interview": interview_serializer.data,
                "is_interviewer": is_interviewer,
            }

            return Response(response_data)

        except RuntimeError as e:
            # LiveKit not configured
            logger.error(f"LiveKit service error: {str(e)}")
            return Response(
                {"error": str(e)}, status=status.HTTP_503_SERVICE_UNAVAILABLE
            )
        except ValueError as e:
            # Validation error
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.exception(f"Error joining interview {id}: {str(e)}")
            return Response(
                {"error": "An unexpected error occurred. Please try again."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


# ========== ADMIN INTERVIEW APIS ==========


class AdminInterviewListAPI(generics.ListAPIView):
    """
    List all interviews (admin only).

    GET /api/admin/interviews/

    Query Parameters:
    - status: Filter by status
    - sender: Filter by sender UUID
    - receiver: Filter by receiver UUID
    """

    serializer_class = InterviewRequestListSerializer
    permission_classes = [IsAuthenticated, IsAdmin]

    @swagger_auto_schema(
        tags=["Interviews"],
        operation_summary="[Admin] List All Interviews",
        operation_description="Admin endpoint to list all interview requests.",
        manual_parameters=[
            openapi.Parameter(
                "status",
                openapi.IN_QUERY,
                type=openapi.TYPE_STRING,
                description="Filter by status",
            ),
        ],
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        queryset = InterviewRequest.objects.select_related(
            "sender", "sender__profile", "receiver", "receiver__profile"
        )

        # Apply filters
        status_filter = self.request.query_params.get("status")
        if status_filter:
            queryset = queryset.filter(status=status_filter)

        return queryset.order_by("-created_at")


class AdminInterviewDetailAPI(generics.RetrieveAPIView):
    """
    Get interview details with audit logs (admin only).

    GET /api/admin/interviews/{id}/
    """

    serializer_class = AdminInterviewRequestSerializer
    permission_classes = [IsAuthenticated, IsAdmin]
    lookup_field = "uuid_id"
    lookup_url_kwarg = "id"  # URL uses 'id' but we look up by 'uuid_id'

    def get_queryset(self):
        return InterviewRequest.objects.select_related(
            "sender", "sender__profile", "receiver", "receiver__profile"
        ).prefetch_related("audit_logs")

    @swagger_auto_schema(
        tags=["Interviews"],
        operation_summary="[Admin] Get Interview Details",
        operation_description="Admin endpoint to get full interview details with audit logs.",
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)


class AdminInterviewActionAPI(APIView):
    """
    Perform admin actions on interviews.

    POST /api/admin/interviews/{id}/action/

    Actions:
    - cancel: Force cancel an interview
    - complete: Mark interview as completed

    Note: Admins CANNOT join LiveKit rooms.
    """

    permission_classes = [IsAuthenticated, IsAdmin]

    @swagger_auto_schema(
        tags=["Interviews"],
        operation_summary="[Admin] Interview Action",
        operation_description="Perform admin action on an interview (cancel or complete).",
        request_body=AdminInterviewActionSerializer,
        responses={
            200: AdminInterviewRequestSerializer,
            400: "Invalid action",
            404: "Interview not found",
        },
    )
    def post(self, request, id):
        interview = get_object_or_404(
            InterviewRequest.objects.select_related(
                "sender", "sender__profile", "receiver", "receiver__profile"
            ),
            uuid_id=id,  # Look up by uuid_id
        )

        serializer = AdminInterviewActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        action = serializer.validated_data["action"]
        reason = serializer.validated_data.get("reason", "Admin action")

        try:
            if action == "cancel":
                interview.cancel(reason=f"[Admin] {reason}")
                action_type = InterviewAuditLog.ACTION_CANCELLED
            elif action == "complete":
                interview.complete()
                action_type = InterviewAuditLog.ACTION_COMPLETED
            else:
                return Response(
                    {"error": f"Unknown action: {action}"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Log admin action
            InterviewAuditLog.log_action(
                interview_request=interview,
                user=request.user,
                action=InterviewAuditLog.ACTION_ADMIN_OVERRIDE,
                details={
                    "action": action,
                    "reason": reason,
                    "original_status": interview.status,
                },
                request=request,
            )

            logger.info(
                f"Admin {request.user.email} performed {action} on interview {id}"
            )

            output_serializer = AdminInterviewRequestSerializer(interview)
            return Response(output_serializer.data)

        except Exception as e:
            logger.error(f"Admin action error on interview {id}: {str(e)}")
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


# ========== LEGACY ENDPOINTS (Keep for backward compatibility) ==========
# These maintain the old URL structure while using new models


class CreateInterviewRequestAPI(InterviewRequestCreateAPI):
    """Legacy endpoint - redirects to new implementation."""

    pass


class SentInterviewRequestsAPI(generics.ListAPIView):
    """Legacy endpoint for sent requests."""

    serializer_class = InterviewRequestListSerializer
    permission_classes = [IsAuthenticated, IsAttender]

    @swagger_auto_schema(auto_schema=None)
    def get_queryset(self):
        return (
            InterviewRequest.objects.filter(sender=self.request.user)
            .select_related(
                "sender", "sender__profile", "receiver", "receiver__profile"
            )
            .order_by("-created_at")
        )


class ReceivedInterviewRequestsAPI(generics.ListAPIView):
    """Legacy endpoint for received requests."""

    serializer_class = InterviewRequestListSerializer
    permission_classes = [IsAuthenticated, IsTaker]

    @swagger_auto_schema(auto_schema=None)
    def get_queryset(self):
        return (
            InterviewRequest.objects.filter(receiver=self.request.user)
            .select_related(
                "sender", "sender__profile", "receiver", "receiver__profile"
            )
            .order_by("-created_at")
        )


class AcceptInterviewRequestAPI(InterviewRequestAcceptAPI):
    """Legacy endpoint - redirects to new implementation."""

    @swagger_auto_schema(auto_schema=None)
    def post(self, request, pk):
        # pk used to be integer, now it's UUID
        return super().post(request, id=pk)


class RejectInterviewRequestAPI(InterviewRequestRejectAPI):
    """Legacy endpoint - redirects to new implementation."""

    @swagger_auto_schema(auto_schema=None)
    def post(self, request, pk):
        return super().post(request, id=pk)


class InterviewDashboardAPI(generics.ListAPIView):
    """
    Interview Dashboard API.

    GET /api/interviews/dashboard/

    Returns all interview requests for the current user (both sent and received).
    Automatically finalizes expired accepted interviews.

    Requirements:
    - User must be authenticated
    """

    permission_classes = [IsAuthenticated]
    serializer_class = InterviewRequestListSerializer

    @swagger_auto_schema(
        tags=["Dashboard"],
        operation_summary="Interview Dashboard",
        operation_description="Get all interview requests for the current user (both sent and received). "
        "Expired accepted interviews are automatically finalized.",
        responses={
            200: InterviewRequestListSerializer(many=True),
            401: "Authentication required",
        },
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        user = self.request.user
        profile = user.profile
        qs = InterviewRequest.objects.select_related(
            "sender__profile",
            "receiver__profile",
        )

        # ATTENDER DASHBOARD
        # ==============================
        if profile.has_role("attender") and not profile.has_role("taker"):
            qs = qs.filter(sender=user)

        # TAKER DASHBOARD (IMPORTANT)
        # ==============================
        elif profile.has_role("taker"):
            from django.db.models import Case, When, BooleanField, Value

            qs = qs.annotate(
                has_pending_feedback=Case(
                    When(
                        Q(interviewer_feedback__isnull=True)
                        | Q(interviewer_feedback__status=FeedbackStatus.PENDING),
                        then=Value(True),
                    ),
                    default=Value(False),
                    output_field=BooleanField(),
                )
            )

        for interview in qs:
            interview.finalize_if_expired()

        return qs.order_by("-created_at")


class InterviewMarkCompleteAPI(APIView):
    """
    Mark an interview as completed.

    POST /api/interviews/requests/{id}/complete/

    Requirements:
    - User must be the receiver (interviewer/taker)
    - Interview must be in 'accepted' status

    Effects:
    - Status changes to 'completed'
    - LiveKit room is deactivated
    - Notifications sent to participants
    """

    permission_classes = [IsAuthenticated, IsTaker]

    @swagger_auto_schema(
        tags=["Interviews"],
        operation_summary="Mark Interview Completed",
        operation_description="Mark an accepted interview as completed. Only the interviewer (taker) can perform this action.",
        responses={
            200: InterviewRequestSerializer,
            400: "Invalid status transition",
            403: "Permission denied - only taker can complete",
            404: "Interview request not found",
        },
    )
    def post(self, request, id):
        interview = get_object_or_404(
            InterviewRequest.objects.select_related(
                "sender", "sender__profile", "receiver", "receiver__profile"
            ),
            uuid_id=id,
        )

        try:
            # Use taker-only method
            interview.mark_completed_by_taker(request.user)

            # Log action
            InterviewAuditLog.log_action(
                interview_request=interview,
                user=request.user,
                action=InterviewAuditLog.ACTION_COMPLETED,
                details={"marked_by": str(request.user.email)},
                request=request,
            )

            logger.info(f"Interview {id} marked as completed by {request.user.email}")

            # Send notification
            try:
                from apps.notifications.services import NotificationService

                NotificationService.notify_interview_completed(
                    interview, completed_by=request.user
                )
            except ImportError:
                pass  # Notifications app not installed

            output_serializer = InterviewRequestSerializer(interview)
            return Response(output_serializer.data)

        except Exception as e:
            logger.error(f"Error completing interview {id}: {str(e)}")
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


class InterviewMarkNotAttendedAPI(APIView):
    """
    Mark an interview as not attended.

    POST /api/interviews/requests/{id}/not-attended/

    Requirements:
    - User must be the receiver (interviewer/taker)
    - Interview must be in 'accepted' status

    Effects:
    - Status changes to 'not_attended'
    - LiveKit room is deactivated
    - Notifications sent to participants
    """

    permission_classes = [IsAuthenticated, IsTaker]

    @swagger_auto_schema(
        tags=["Interviews"],
        operation_summary="Mark Interview Not Attended",
        operation_description="Mark an accepted interview as not attended. Only the interviewer (taker) can perform this action.",
        responses={
            200: InterviewRequestSerializer,
            400: "Invalid status transition",
            403: "Permission denied - only taker can mark as not attended",
            404: "Interview request not found",
        },
    )
    def post(self, request, id):
        interview = get_object_or_404(
            InterviewRequest.objects.select_related(
                "sender", "sender__profile", "receiver", "receiver__profile"
            ),
            uuid_id=id,
        )

        try:
            # Use taker-only method
            interview.mark_not_attended_by_taker(request.user)

            # Log action
            InterviewAuditLog.log_action(
                interview_request=interview,
                user=request.user,
                action=InterviewAuditLog.ACTION_NOT_ATTENDED,
                details={"marked_by": str(request.user.email)},
                request=request,
            )

            logger.info(
                f"Interview {id} marked as not attended by {request.user.email}"
            )

            # Send notification
            try:
                from apps.notifications.services import NotificationService

                NotificationService.notify_interview_not_attended(
                    interview, marked_by=request.user
                )
            except ImportError:
                pass  # Notifications app not installed

            output_serializer = InterviewRequestSerializer(interview)
            return Response(output_serializer.data)

        except Exception as e:
            logger.error(f"Error marking interview {id} as not attended: {str(e)}")
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


# ========== NEW LIVEKIT ROOM CONTROL APIS ==========


class InterviewRoomControlsAPI(APIView):
    """
    Control interview room participants (mute/unmute/eject).

    POST /api/interviews/{id}/room/controls/

    Requirements:
    - User must be the interviewer (receiver/taker)
    - Interview must be in 'accepted' status and joinable

    Actions:
    - mute: Mute participant's audio (and optionally video)
    - unmute: Unmute participant's audio (and optionally video)
    - eject: Remove participant from room
    - end: End the entire interview room

    Request Body:
    - action: 'mute' | 'unmute' | 'eject' | 'end'
    - identity: Target participant identity (required for mute/unmute/eject)
    - audio_only: Boolean, default True (for mute/unmute)
    """

    permission_classes = [IsAuthenticated, IsTaker]

    @swagger_auto_schema(
        tags=["Interviews"],
        operation_summary="Interview Room Controls",
        operation_description="Control interview room - mute/unmute/eject participants or end room. "
        "Only the interviewer can perform these actions.",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            required=["action"],
            properties={
                "action": openapi.Schema(
                    type=openapi.TYPE_STRING,
                    enum=["mute", "unmute", "eject", "end"],
                    description="Action to perform",
                ),
                "identity": openapi.Schema(
                    type=openapi.TYPE_STRING,
                    description="Target participant identity (required for mute/unmute/eject)",
                ),
                "audio_only": openapi.Schema(
                    type=openapi.TYPE_BOOLEAN,
                    default=True,
                    description="If true, only mute/unmute audio. If false, also affects video.",
                ),
            },
        ),
        responses={
            200: openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    "status": openapi.Schema(type=openapi.TYPE_STRING),
                    "room_name": openapi.Schema(type=openapi.TYPE_STRING),
                    "action": openapi.Schema(type=openapi.TYPE_STRING),
                },
            ),
            400: "Invalid action or missing parameters",
            403: "Permission denied - only interviewer can control room",
            404: "Interview not found",
            503: "LiveKit service unavailable",
        },
    )
    def post(self, request, id):
        from asgiref.sync import async_to_sync

        interview = get_object_or_404(
            InterviewRequest.objects.select_related(
                "sender", "sender__profile", "receiver", "receiver__profile"
            ),
            uuid_id=id,
        )

        # Only the receiver (interviewer) can control the room
        if request.user != interview.receiver:
            return Response(
                {"error": "Only the interviewer can control the room."},
                status=status.HTTP_403_FORBIDDEN,
            )

        # Check interview is accepted and joinable
        if interview.status != "accepted":
            return Response(
                {"error": f"Interview is not in progress (status: {interview.status})"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        action = request.data.get("action")
        identity = request.data.get("identity")
        audio_only = request.data.get("audio_only", True)

        if not action:
            return Response(
                {"error": "Action is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if action in ["mute", "unmute", "eject"] and not identity:
            return Response(
                {"error": f"Identity is required for {action} action"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        livekit = get_livekit_service()
        room_name = f"interview-{interview.uuid_id}"

        try:
            if action == "mute":
                result = async_to_sync(livekit.mute_participant)(
                    room_name, identity, audio_only=audio_only
                )
            elif action == "unmute":
                result = async_to_sync(livekit.unmute_participant)(
                    room_name, identity, audio_only=audio_only
                )
            elif action == "eject":
                result = async_to_sync(livekit.eject_participant)(room_name, identity)
            elif action == "end":
                result = async_to_sync(livekit.end_interview_room)(room_name)
            else:
                return Response(
                    {"error": f"Unknown action: {action}"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Log the action
            InterviewAuditLog.log_action(
                interview_request=interview,
                user=request.user,
                action=f"room_{action}",
                details={
                    "room_name": room_name,
                    "target_identity": identity,
                    "audio_only": audio_only if action in ["mute", "unmute"] else None,
                },
                request=request,
            )

            logger.info(
                f"Room control action '{action}' performed by {request.user.email} "
                f"on room {room_name}"
            )

            return Response({**result, "action": action})

        except RuntimeError as e:
            logger.error(f"LiveKit service error: {str(e)}")
            return Response(
                {"error": str(e)}, status=status.HTTP_503_SERVICE_UNAVAILABLE
            )
        except Exception as e:
            logger.exception(f"Error performing room control action: {str(e)}")
            return Response(
                {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class InterviewRoomInfoAPI(APIView):
    """
    Get live room information and participants.

    GET /api/interviews/{id}/room/info/

    Requirements:
    - User must be a participant (sender or receiver)

    Returns:
    - Room name, active status
    - Participant count and list
    - Room metadata
    """

    permission_classes = [IsAuthenticated, IsInterviewParticipant]

    @swagger_auto_schema(
        tags=["Interviews"],
        operation_summary="Get Interview Room Info",
        operation_description="Get live information about the interview room including participants.",
        responses={
            200: openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    "room_name": openapi.Schema(type=openapi.TYPE_STRING),
                    "is_active": openapi.Schema(type=openapi.TYPE_BOOLEAN),
                    "participant_count": openapi.Schema(type=openapi.TYPE_INTEGER),
                    "participants": openapi.Schema(
                        type=openapi.TYPE_ARRAY,
                        items=openapi.Schema(
                            type=openapi.TYPE_OBJECT,
                            properties={
                                "identity": openapi.Schema(type=openapi.TYPE_STRING),
                                "name": openapi.Schema(type=openapi.TYPE_STRING),
                                "is_publisher": openapi.Schema(
                                    type=openapi.TYPE_BOOLEAN
                                ),
                            },
                        ),
                    ),
                },
            ),
            404: "Interview or room not found",
            503: "LiveKit service unavailable",
        },
    )
    def get(self, request, id):
        from asgiref.sync import async_to_sync

        interview = get_object_or_404(
            InterviewRequest.objects.select_related(
                "sender", "sender__profile", "receiver", "receiver__profile"
            ),
            uuid_id=id,
        )

        self.check_object_permissions(request, interview)

        livekit = get_livekit_service()
        room_name = f"interview-{interview.uuid_id}"

        try:
            room_info = async_to_sync(livekit.get_room_info)(room_name)

            if room_info is None:
                return Response(
                    {
                        "room_name": room_name,
                        "is_active": False,
                        "participant_count": 0,
                        "participants": [],
                        "message": "Room does not exist yet",
                    }
                )

            return Response(room_info)

        except RuntimeError as e:
            logger.error(f"LiveKit service error: {str(e)}")
            return Response(
                {"error": str(e)}, status=status.HTTP_503_SERVICE_UNAVAILABLE
            )
        except Exception as e:
            logger.exception(f"Error getting room info: {str(e)}")
            return Response(
                {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class ActiveRoomsAPI(APIView):
    """
    List all active interview rooms (admin only).

    GET /api/interviews/rooms/active/

    Requirements:
    - User must be admin

    Returns:
    - List of active interview rooms with participant counts
    """

    permission_classes = [IsAuthenticated, IsAdmin]

    @swagger_auto_schema(
        tags=["Interviews"],
        operation_summary="[Admin] List Active Rooms",
        operation_description="Get all active interview rooms. Admin only.",
        responses={
            200: openapi.Schema(
                type=openapi.TYPE_ARRAY,
                items=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        "room_name": openapi.Schema(type=openapi.TYPE_STRING),
                        "num_participants": openapi.Schema(type=openapi.TYPE_INTEGER),
                        "created_at": openapi.Schema(type=openapi.TYPE_INTEGER),
                    },
                ),
            ),
            403: "Admin access required",
            503: "LiveKit service unavailable",
        },
    )
    def get(self, request):
        from asgiref.sync import async_to_sync

        livekit = get_livekit_service()

        try:
            active_rooms = async_to_sync(livekit.list_active_rooms)()
            return Response({"rooms": active_rooms, "count": len(active_rooms)})

        except RuntimeError as e:
            logger.error(f"LiveKit service error: {str(e)}")
            return Response(
                {"error": str(e)}, status=status.HTTP_503_SERVICE_UNAVAILABLE
            )
        except Exception as e:
            logger.exception(f"Error listing active rooms: {str(e)}")
            return Response(
                {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class EnsureInterviewRoomAPI(APIView):
    """
    Ensure interview room exists before joining.

    POST /api/interviews/{id}/room/ensure/

    This is called by the frontend before joining to ensure the room exists.
    Creates the room with interview-specific settings if it doesn't exist.

    Requirements:
    - User must be a participant
    - Interview must be accepted

    Returns:
    - Room info (name, sid, created status)
    """

    permission_classes = [IsAuthenticated, CanJoinInterview]

    @swagger_auto_schema(
        tags=["Interviews"],
        operation_summary="Ensure Interview Room Exists",
        operation_description="Create interview room if it doesn't exist. "
        "Call this before joining to ensure room is ready.",
        responses={
            200: openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    "room_name": openapi.Schema(type=openapi.TYPE_STRING),
                    "sid": openapi.Schema(type=openapi.TYPE_STRING),
                    "already_existed": openapi.Schema(type=openapi.TYPE_BOOLEAN),
                    "num_participants": openapi.Schema(type=openapi.TYPE_INTEGER),
                },
            ),
            400: "Interview not accepted",
            403: "Permission denied",
            404: "Interview not found",
            503: "LiveKit service unavailable",
        },
    )
    def post(self, request, id):
        from asgiref.sync import async_to_sync

        interview = get_object_or_404(
            InterviewRequest.objects.select_related(
                "sender", "sender__profile", "receiver", "receiver__profile"
            ),
            uuid_id=id,
        )

        self.check_object_permissions(request, interview)

        livekit = get_livekit_service()
        room_name = f"interview-{interview.uuid_id}"

        try:
            result = async_to_sync(livekit.ensure_room_exists)(
                room_name, str(interview.uuid_id)
            )

            logger.info(
                f"Room {room_name} ensured by {request.user.email} "
                f"(already_existed: {result.get('already_existed', False)})"
            )

            return Response(result)

        except RuntimeError as e:
            logger.error(f"LiveKit service error: {str(e)}")
            return Response(
                {"error": str(e)}, status=status.HTTP_503_SERVICE_UNAVAILABLE
            )
        except Exception as e:
            logger.exception(f"Error ensuring room exists: {str(e)}")
            return Response(
                {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
