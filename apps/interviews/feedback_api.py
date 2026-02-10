# apps/interviews/feedback_api.py
"""
API view for interviewer feedback submission.

Endpoint: POST /api/interviews/{id}/feedback/interviewer/

Only the taker (interviewer) can submit feedback.
Interview must be in 'accepted' or 'completed' status.
Feedback can only be submitted once.
"""

import logging
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404
from django.core.exceptions import ValidationError
from django.db import transaction
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi

from .models import InterviewRequest
from .feedback_models import InterviewerFeedback, FeedbackStatus
from .feedback_serializers import (
    InterviewerFeedbackSerializer,
    InterviewerFeedbackSubmitSerializer,
    InterviewerFeedbackResponseSerializer,
)

logger = logging.getLogger(__name__)


class InterviewerFeedbackAPI(APIView):
    """
    API endpoint for interviewer feedback submission.

    GET: Retrieve existing feedback for an interview
    POST: Submit new feedback (once per interview)

    Access Control:
    - Only interview participants can GET
    - Only the taker (interviewer) can POST
    """

    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_summary="Get Interviewer Feedback",
        operation_description="""
        Retrieve interviewer feedback for a specific interview.
        
        **Access:** Only interview participants (sender or receiver) can view.
        """,
        tags=["Interview - Feedback"],
        responses={
            200: openapi.Response(
                description="Feedback retrieved successfully",
                schema=InterviewerFeedbackSerializer,
            ),
            403: openapi.Response(description="Not authorized to view this feedback"),
            404: openapi.Response(description="Interview or feedback not found"),
        },
    )
    def get(self, request, interview_id):
        """Retrieve feedback for an interview."""

        # Get interview
        interview = get_object_or_404(
            InterviewRequest.objects.select_related("sender", "receiver"),
            uuid_id=interview_id,
        )

        # Check permission: only participants can view
        user = request.user
        if (
            user != interview.sender
            and user != interview.receiver
            and not user.is_staff
        ):
            return Response(
                {"detail": "You are not authorized to view this feedback."},
                status=status.HTTP_403_FORBIDDEN,
            )

        # Get feedback
        try:
            feedback = interview.interviewer_feedback
            serializer = InterviewerFeedbackSerializer(feedback)
            return Response(serializer.data, status=status.HTTP_200_OK)
        except InterviewerFeedback.DoesNotExist:
            return Response(
                {"detail": "No feedback has been submitted for this interview yet."},
                status=status.HTTP_404_NOT_FOUND,
            )

    @swagger_auto_schema(
        operation_summary="Submit Interviewer Feedback",
        operation_description="""
        Submit mandatory feedback as the interviewer (taker).
        
        **Access:** Only the interviewer (taker/receiver) can submit.
        
        **Interview Status:** Must be 'accepted' or 'completed'.
        
        **All fields are required:**
        - 4 questions with both rating (1-5) AND text explanation
        - Overall feedback text
        
        **On Success:**
        - Feedback status set to 'submitted'
        - Credit payout hook is triggered
        
        **Note:** Feedback can only be submitted once per interview.
        """,
        tags=["Interview - Feedback"],
        request_body=InterviewerFeedbackSubmitSerializer,
        responses={
            201: openapi.Response(
                description="Feedback submitted successfully",
                schema=InterviewerFeedbackResponseSerializer,
                examples={
                    "application/json": {
                        "detail": "Feedback submitted successfully. Credit payout triggered.",
                        "feedback": {
                            "id": "uuid",
                            "status": "submitted",
                            "average_rating": 4.25,
                        },
                        "credits_pending": 100,
                    }
                },
            ),
            400: openapi.Response(
                description="Validation error or feedback already submitted",
                examples={
                    "application/json": {
                        "detail": "Feedback has already been submitted for this interview."
                    }
                },
            ),
            403: openapi.Response(
                description="Only the interviewer can submit feedback",
                examples={
                    "application/json": {
                        "detail": "Only the interviewer (taker) can submit feedback."
                    }
                },
            ),
            404: openapi.Response(description="Interview not found"),
        },
    )
    @transaction.atomic
    def post(self, request, interview_id):
        """Submit feedback for an interview."""

        # Get interview with lock for atomic operation
        interview = get_object_or_404(
            InterviewRequest.objects.select_related("sender", "receiver"),
            uuid_id=interview_id,
        )

        if hasattr(interview, "interviewer_feedback"):
            return Response(
                {"detail": "Feedback already submitted for this interview."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user = request.user

        # ===== ACCESS CONTROL =====
        # Only the taker (receiver) can submit feedback
        if user != interview.receiver:
            return Response(
                {"detail": "Only the interviewer (taker) can submit feedback."},
                status=status.HTTP_403_FORBIDDEN,
            )

        # ===== STATUS VALIDATION =====
        valid_statuses = ["accepted", "completed"]
        if interview.status not in valid_statuses:
            return Response(
                {
                    "detail": f"Cannot submit feedback for interview with status '{interview.status}'.",
                    "allowed_statuses": valid_statuses,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # ===== CHECK EXISTING FEEDBACK =====
        try:
            existing = interview.interviewer_feedback
            if existing.status == FeedbackStatus.SUBMITTED:
                return Response(
                    {
                        "detail": "Feedback has already been submitted for this interview."
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )
        except InterviewerFeedback.DoesNotExist:
            existing = None

        # ===== VALIDATE INPUT =====
        serializer = InterviewerFeedbackSubmitSerializer(
            data=request.data,
            context={"request": request, "interview_request": interview},
        )
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data

        # ===== CREATE OR UPDATE FEEDBACK =====
        try:
            if existing:
                feedback = existing
            else:
                feedback = InterviewerFeedback(
                    interview_request=interview, interviewer=user
                )

            # Set all fields
            feedback.problem_understanding_rating = data["problem_understanding_rating"]
            feedback.problem_understanding_text = data["problem_understanding_text"]
            feedback.solution_approach_rating = data["solution_approach_rating"]
            feedback.solution_approach_text = data["solution_approach_text"]
            feedback.implementation_skill_rating = data["implementation_skill_rating"]
            feedback.implementation_skill_text = data["implementation_skill_text"]
            feedback.communication_rating = data["communication_rating"]
            feedback.communication_text = data["communication_text"]
            feedback.overall_feedback = data["overall_feedback"]

            # Save first (signals will handle credit payout)
            feedback.save()

            # Submit (marks as submitted and triggers signal)
            feedback.submit()

            logger.info(
                f"Feedback submitted for interview {interview.uuid_id} "
                f"by {user.email}"
            )

            # Prepare response
            response_serializer = InterviewerFeedbackSerializer(feedback)

            return Response(
                {
                    "detail": "Feedback submitted successfully. Credit payout triggered.",
                    "feedback": response_serializer.data,
                    "credits_pending": interview.credits,
                },
                status=status.HTTP_201_CREATED,
            )

        except ValidationError as e:
            return Response(
                {"detail": str(e.message if hasattr(e, "message") else e)},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception as e:
            logger.error(f"Error submitting feedback: {str(e)}")
            return Response(
                {"detail": "An error occurred while submitting feedback."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class CandidateFeedbackAPI(APIView):
    """
    API endpoint for optional candidate (attender) feedback.

    GET: Retrieve existing candidate feedback
    POST: Submit candidate feedback (optional ratings)

    Access Control:
    - Only interview participants can GET
    - Only the candidate (attender/sender) can POST

    Note: This does NOT affect credit payouts.
    """

    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_summary="Get Candidate Feedback",
        operation_description="""
        Retrieve candidate feedback for a specific interview.
        
        **Access:** Only interview participants (sender or receiver) can view.
        """,
        tags=["Interview - Feedback"],
        responses={
            200: openapi.Response(description="Feedback retrieved successfully"),
            403: openapi.Response(description="Not authorized to view this feedback"),
            404: openapi.Response(description="Interview or feedback not found"),
        },
    )
    def get(self, request, interview_id):
        """Retrieve candidate feedback for an interview."""
        from .feedback_models import CandidateFeedback
        from .feedback_serializers import CandidateFeedbackSerializer

        # Get interview
        interview = get_object_or_404(
            InterviewRequest.objects.select_related("sender", "receiver"),
            uuid_id=interview_id,
        )

        # Check permission: only participants can view
        user = request.user
        if (
            user != interview.sender
            and user != interview.receiver
            and not user.is_staff
        ):
            return Response(
                {"detail": "You are not authorized to view this feedback."},
                status=status.HTTP_403_FORBIDDEN,
            )

        # Get feedback
        try:
            feedback = interview.candidate_feedback
            serializer = CandidateFeedbackSerializer(feedback)
            return Response(serializer.data, status=status.HTTP_200_OK)
        except CandidateFeedback.DoesNotExist:
            return Response(
                {
                    "detail": "No candidate feedback has been submitted for this interview yet."
                },
                status=status.HTTP_404_NOT_FOUND,
            )

    @swagger_auto_schema(
        operation_summary="Submit Candidate Feedback (Optional)",
        operation_description="""
        Submit optional feedback as the candidate (attender).
        
        **Access:** Only the candidate (attender/sender) can submit.
        
        **Interview Status:** Must be 'accepted', 'completed', or 'not_attended'.
        
        **All fields are optional:**
        - 4 rating questions (1-5 scale)
        - Comments (text)
        - Would recommend (boolean)
        
        **At least one field must be provided.**
        
        **Note:** This feedback is optional and does NOT affect credit payouts.
        """,
        tags=["Interview - Feedback"],
        responses={
            201: openapi.Response(
                description="Feedback submitted successfully",
                examples={
                    "application/json": {
                        "detail": "Feedback submitted successfully.",
                        "feedback": {
                            "id": "uuid",
                            "overall_experience_rating": 4,
                            "average_rating": 4.0,
                        },
                    }
                },
            ),
            200: openapi.Response(description="Feedback updated successfully"),
            400: openapi.Response(description="Validation error"),
            403: openapi.Response(description="Only the candidate can submit feedback"),
            404: openapi.Response(description="Interview not found"),
        },
    )
    @transaction.atomic
    def post(self, request, interview_id):
        """Submit or update candidate feedback."""
        from .feedback_models import CandidateFeedback
        from .feedback_serializers import (
            CandidateFeedbackSerializer,
            CandidateFeedbackSubmitSerializer,
        )

        # Get interview
        interview = get_object_or_404(
            InterviewRequest.objects.select_related("sender", "receiver"),
            uuid_id=interview_id,
        )

        user = request.user

        # ===== ACCESS CONTROL =====
        # Only the candidate (sender) can submit feedback
        if user != interview.sender:
            return Response(
                {"detail": "Only the candidate (attender) can submit feedback."},
                status=status.HTTP_403_FORBIDDEN,
            )

        # ===== STATUS VALIDATION =====
        valid_statuses = ["accepted", "completed", "not_attended"]
        if interview.status not in valid_statuses:
            return Response(
                {
                    "detail": f"Cannot submit feedback for interview with status '{interview.status}'.",
                    "allowed_statuses": valid_statuses,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # ===== VALIDATE INPUT =====
        serializer = CandidateFeedbackSubmitSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data

        # ===== CREATE OR UPDATE FEEDBACK =====
        try:
            feedback, created = CandidateFeedback.objects.get_or_create(
                interview_request=interview, defaults={"candidate": user}
            )

            # Update all provided fields
            if "overall_experience_rating" in data:
                feedback.overall_experience_rating = data["overall_experience_rating"]
            if "professionalism_rating" in data:
                feedback.professionalism_rating = data["professionalism_rating"]
            if "question_clarity_rating" in data:
                feedback.question_clarity_rating = data["question_clarity_rating"]
            if "feedback_quality_rating" in data:
                feedback.feedback_quality_rating = data["feedback_quality_rating"]
            if "comments" in data:
                feedback.comments = data["comments"]
            if "would_recommend" in data:
                feedback.would_recommend = data["would_recommend"]

            feedback.candidate = user
            feedback.save()

            logger.info(
                f"Candidate feedback {'created' if created else 'updated'} "
                f"for interview {interview.uuid_id} by {user.email}"
            )

            # Prepare response
            response_serializer = CandidateFeedbackSerializer(feedback)

            return Response(
                {
                    "detail": f"Feedback {'submitted' if created else 'updated'} successfully.",
                    "feedback": response_serializer.data,
                },
                status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
            )

        except ValidationError as e:
            return Response(
                {"detail": str(e.message if hasattr(e, "message") else e)},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception as e:
            logger.error(f"Error submitting candidate feedback: {str(e)}")
            return Response(
                {"detail": "An error occurred while submitting feedback."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
