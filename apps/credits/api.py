# apps/credits/api.py
"""
API views for credit system.

Endpoints:
- GET /api/credits/balance/ - Get current credit balance (attender)
- GET /api/credits/earnings/ - Get taker earnings summary
- GET /api/credits/transactions/ - Get transaction history
- GET /api/credits/summary/ - Get combined credit summary
- GET /api/credits/check/ - Check interview affordability

Note: Feedback endpoints are now in apps.interviews.feedback_api
Note: Admin endpoints have been removed
"""

import logging
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.generics import ListAPIView
from django.shortcuts import get_object_or_404
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi

from .models import CreditBalance, CreditTransaction, TakerEarnings
from .serializers import (
    CreditBalanceSerializer,
    CreditTransactionSerializer,
    TakerEarningsSerializer,
    CreditSummarySerializer,
)
from .services import CreditService

logger = logging.getLogger(__name__)


class CreditBalanceAPI(APIView):
    """
    Get current credit balance for the authenticated user.
    
    Only applicable for attenders (users who spend credits).
    """
    permission_classes = [IsAuthenticated]
    
    @swagger_auto_schema(
        operation_summary="Get Credit Balance",
        operation_description="Get the current credit balance for the authenticated attender.",
        tags=['Credits'],
        responses={
            200: openapi.Response(
                description="Credit balance retrieved successfully",
                schema=CreditBalanceSerializer
            ),
            404: openapi.Response(description="No balance found (user is not an attender)"),
        }
    )
    def get(self, request):
        user = request.user
        
        try:
            balance = user.credit_balance
            serializer = CreditBalanceSerializer(balance)
            return Response(serializer.data, status=status.HTTP_200_OK)
        except CreditBalance.DoesNotExist:
            # Create balance if user is attender
            if hasattr(user, 'profile') and user.profile.is_attender():
                balance = CreditService.get_or_create_balance(user)
                serializer = CreditBalanceSerializer(balance)
                return Response(serializer.data, status=status.HTTP_200_OK)
            
            return Response(
                {"detail": "No credit balance found. Balance is only available for attenders."},
                status=status.HTTP_404_NOT_FOUND
            )


class TakerEarningsAPI(APIView):
    """
    Get earnings summary for the authenticated taker (interviewer).
    """
    permission_classes = [IsAuthenticated]
    
    @swagger_auto_schema(
        operation_summary="Get Taker Earnings",
        operation_description="Get earnings summary for the authenticated interviewer.",
        tags=['Credits'],
        responses={
            200: openapi.Response(
                description="Earnings retrieved successfully",
                schema=TakerEarningsSerializer
            ),
            404: openapi.Response(description="No earnings found (user is not a taker)"),
        }
    )
    def get(self, request):
        user = request.user
        
        try:
            earnings = user.taker_earnings
            serializer = TakerEarningsSerializer(earnings)
            return Response(serializer.data, status=status.HTTP_200_OK)
        except TakerEarnings.DoesNotExist:
            # Create earnings record if user is taker
            if hasattr(user, 'profile') and user.profile.is_taker():
                earnings, _ = TakerEarnings.objects.get_or_create(user=user)
                serializer = TakerEarningsSerializer(earnings)
                return Response(serializer.data, status=status.HTTP_200_OK)
            
            return Response(
                {"detail": "No earnings found. Earnings are only available for interviewers."},
                status=status.HTTP_404_NOT_FOUND
            )


class CreditTransactionListAPI(ListAPIView):
    """
    Get credit transaction history for the authenticated user.
    """
    permission_classes = [IsAuthenticated]
    serializer_class = CreditTransactionSerializer
    
    @swagger_auto_schema(
        operation_summary="Get Transaction History",
        operation_description="Get credit transaction history for the authenticated user.",
        tags=['Credits'],
        manual_parameters=[
            openapi.Parameter(
                'limit', openapi.IN_QUERY,
                description='Maximum number of transactions to return (default: 50)',
                type=openapi.TYPE_INTEGER
            ),
            openapi.Parameter(
                'type', openapi.IN_QUERY,
                description='Filter by transaction type',
                type=openapi.TYPE_STRING,
                enum=['initial_credit', 'interview_debit', 'interview_credit', 'refund']
            ),
        ]
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)
    
    def get_queryset(self):
        user = self.request.user
        limit = int(self.request.query_params.get('limit', 50))
        txn_type = self.request.query_params.get('type')
        
        queryset = CreditTransaction.objects.filter(user=user).order_by('-created_at')
        
        if txn_type:
            queryset = queryset.filter(transaction_type=txn_type)
        
        return queryset[:limit]


class CreditSummaryAPI(APIView):
    """
    Get combined credit summary for dashboard.
    
    Includes both attender balance and taker earnings (if applicable).
    """
    permission_classes = [IsAuthenticated]
    
    @swagger_auto_schema(
        operation_summary="Get Credit Summary",
        operation_description="Get combined credit summary including balance (for attenders) and earnings (for takers).",
        tags=['Credits'],
        responses={
            200: openapi.Response(
                description="Credit summary retrieved successfully",
                schema=CreditSummarySerializer
            ),
        }
    )
    def get(self, request):
        user = request.user
        profile = getattr(user, 'profile', None)
        
        is_attender = profile.is_attender() if profile else False
        is_taker = profile.is_taker() if profile else False
        
        # Get attender balance
        balance_data = CreditService.get_balance(user)
        
        # Get taker earnings
        taker_earnings = None
        taker_pending = None
        if is_taker:
            earnings_data = CreditService.get_taker_earnings(user)
            taker_earnings = earnings_data.get('total_earned', 0)
            taker_pending = earnings_data.get('pending_credits', 0)
        
        summary = {
            **balance_data,
            'taker_total_earned': taker_earnings,
            'taker_pending_credits': taker_pending,
            'is_attender': is_attender,
            'is_taker': is_taker,
        }
        
        serializer = CreditSummarySerializer(summary)
        return Response(serializer.data, status=status.HTTP_200_OK)


class CheckCreditsAPI(APIView):
    """
    Check if user can afford an interview before requesting.
    """
    permission_classes = [IsAuthenticated]
    
    @swagger_auto_schema(
        operation_summary="Check Interview Affordability",
        operation_description="Check if user has enough credits for an interview before requesting.",
        tags=['Credits'],
        manual_parameters=[
            openapi.Parameter(
                'taker_uuid', openapi.IN_QUERY,
                description='UUID of the interviewer profile',
                type=openapi.TYPE_STRING,
                required=True
            ),
        ],
        responses={
            200: openapi.Response(
                description="Affordability check result",
                examples={
                    "application/json": {
                        "can_afford": True,
                        "available_balance": 1000,
                        "credits_required": 100,
                        "balance_after": 900,
                    }
                }
            ),
        }
    )
    def get(self, request):
        from apps.profiles.models import UserProfile
        
        taker_uuid = request.query_params.get('taker_uuid')
        if not taker_uuid:
            return Response(
                {"detail": "taker_uuid query parameter is required."},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            taker_profile = UserProfile.objects.select_related('user').get(public_id=taker_uuid)
        except UserProfile.DoesNotExist:
            return Response(
                {"detail": "Interviewer not found."},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Get credits required from interviewer profile
        try:
            credits_required = taker_profile.interviewer_profile.credits_per_interview
        except Exception:
            credits_required = 0
        
        # Check if attender can afford
        can_afford, balance, message = CreditService.check_can_request_interview(
            request.user,
            credits_required
        )
        
        return Response({
            "can_afford": can_afford,
            "available_balance": balance,
            "credits_required": credits_required,
            "balance_after": balance - credits_required if can_afford else 0,
            "message": message,
        }, status=status.HTTP_200_OK)
