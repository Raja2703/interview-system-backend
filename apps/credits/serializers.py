# apps/credits/serializers.py
"""
Serializers for credit system API endpoints.

Note: Feedback serializers have been removed - feedback is now in apps.interviews.feedback_serializers
Note: Admin adjustment serializer has been removed
"""

from rest_framework import serializers
from .models import (
    CreditBalance,
    CreditTransaction,
    TakerEarnings,
    TransactionType,
    TransactionStatus,
)


class CreditBalanceSerializer(serializers.ModelSerializer):
    """Serializer for credit balance information."""
    
    user_email = serializers.EmailField(source='user.email', read_only=True)
    available_balance = serializers.IntegerField(source='balance', read_only=True)
    total_balance = serializers.SerializerMethodField()
    
    class Meta:
        model = CreditBalance
        fields = [
            'id',
            'user_email',
            'available_balance',
            'escrow_balance',
            'total_balance',
            'total_earned',
            'total_spent',
            'has_received_initial_credits',
            'created_at',
            'updated_at',
        ]
        read_only_fields = fields
    
    def get_total_balance(self, obj):
        return obj.total_balance


class CreditTransactionSerializer(serializers.ModelSerializer):
    """Serializer for credit transaction history."""
    
    user_email = serializers.EmailField(source='user.email', read_only=True)
    interview_uuid = serializers.SerializerMethodField()
    transaction_type_display = serializers.CharField(
        source='get_transaction_type_display',
        read_only=True
    )
    status_display = serializers.CharField(
        source='get_status_display',
        read_only=True
    )
    
    class Meta:
        model = CreditTransaction
        fields = [
            'id',
            'user_email',
            'transaction_type',
            'transaction_type_display',
            'status',
            'status_display',
            'amount',
            'balance_after',
            'description',
            'interview_uuid',
            'created_at',
        ]
        read_only_fields = fields
    
    def get_interview_uuid(self, obj):
        if obj.interview_request:
            return str(obj.interview_request.uuid_id)
        return None


class TakerEarningsSerializer(serializers.ModelSerializer):
    """Serializer for taker earnings summary."""
    
    user_email = serializers.EmailField(source='user.email', read_only=True)
    available_earnings = serializers.SerializerMethodField()
    
    class Meta:
        model = TakerEarnings
        fields = [
            'id',
            'user_email',
            'total_earned',
            'pending_credits',
            'interviews_completed',
            'feedbacks_submitted',
            'available_earnings',
            'created_at',
            'updated_at',
        ]
        read_only_fields = fields
    
    def get_available_earnings(self, obj):
        return obj.total_earned


class CreditSummarySerializer(serializers.Serializer):
    """Combined credit summary for dashboard."""
    
    # For attenders
    available_balance = serializers.IntegerField(help_text='Available credits for spending')
    escrow_balance = serializers.IntegerField(help_text='Credits held in pending interviews')
    total_balance = serializers.IntegerField(help_text='Total balance including escrow')
    total_earned = serializers.IntegerField(help_text='Total credits ever received')
    total_spent = serializers.IntegerField(help_text='Total credits ever spent')
    has_received_initial_credits = serializers.BooleanField()
    
    # For takers
    taker_total_earned = serializers.IntegerField(
        required=False, allow_null=True,
        help_text='Total credits earned as interviewer'
    )
    taker_pending_credits = serializers.IntegerField(
        required=False, allow_null=True,
        help_text='Credits pending feedback submission'
    )
    
    # User role info
    is_attender = serializers.BooleanField()
    is_taker = serializers.BooleanField()
