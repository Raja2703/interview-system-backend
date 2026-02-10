# apps/credits/services.py
"""
Credit service for atomic credit operations.

Provides:
- Initial credit award for new attenders
- Credit debit for interview requests
- Credit release to takers after feedback
- Credit refunds for rejections/cancellations
- Balance and transaction queries

Note: Feedback is handled via apps.interviews.feedback_models.InterviewerFeedback
Note: Admin operations have been removed

All operations are atomic and create audit trails.
"""

import logging
from django.db import transaction
from django.core.exceptions import ValidationError
from django.utils import timezone

from .models import (
    CreditBalance,
    CreditTransaction,
    TakerEarnings,
    TransactionType,
    TransactionStatus,
)

logger = logging.getLogger(__name__)

# Configuration constants


INITIAL_ATTENDER_CREDITS = 1000



class CreditService:
    """
    Service class for all credit-related operations.
    
    All methods are atomic and create transaction records.
    """
    
    # ========== BALANCE MANAGEMENT ==========
    
    @staticmethod
    def get_or_create_balance(user):
        """
        Get or create credit balance for a user.
        
        Args:
            user: User instance
            
        Returns:
            CreditBalance instance
        """
        balance, created = CreditBalance.objects.get_or_create(user=user)
        if created:
            logger.info(f"Created credit balance for user {user.email}")
        return balance
    
    @staticmethod
    def get_balance(user):
        """
        Get current balance for a user.
        
        Args:
            user: User instance
            
        Returns:
            dict with balance information
        """
        try:
            balance = user.credit_balance
            return balance.get_balance_summary()
        except CreditBalance.DoesNotExist:
            return {
                'available_balance': 0,
                'escrow_balance': 0,
                'total_balance': 0,
                'total_earned': 0,
                'total_spent': 0,
                'has_received_initial_credits': False,
            }
    
    # ========== INITIAL CREDITS ==========
    
    INITIAL_ATTENDER_CREDITS = 1000

    @classmethod
    @transaction.atomic
    def award_initial_credits(cls, user):
        balance, _ = CreditBalance.objects.select_for_update().get_or_create(user=user)

        if balance.has_received_initial_credits:
            return False, "Already credited", None

        # Ensure user has a profile and is an attender
        if not hasattr(user, 'profile') or not user.profile.is_attender():
            return False, "User is not an attender", None

        amount = cls.INITIAL_ATTENDER_CREDITS

        # Update actual model fields (not the read-only properties)
        balance.balance += amount
        balance.total_earned += amount
        balance.has_received_initial_credits = True
        balance.save(update_fields=['balance', 'total_earned', 'has_received_initial_credits', 'updated_at'])

        txn = CreditTransaction.objects.create(
            user=user,
            transaction_type=TransactionType.INITIAL_CREDIT,
            status=TransactionStatus.COMPLETED,
            amount=amount,
            balance_after=balance.balance,
            description="Initial credits for attender role",
        )

        return True, "Initial credits awarded", txn
    
    # ========== INTERVIEW REQUEST (DEBIT TO ESCROW) ==========
    
    @classmethod
    @transaction.atomic
    def debit_for_interview_request(cls, interview_request, user=None):
        """
        Debit credits from attender when they request an interview.
        Credits are moved to escrow until interview is completed/cancelled.
        
        Args:
            interview_request: InterviewRequest instance
            user: User initiating the request (optional, for audit)
            
        Returns:
            tuple: (success: bool, message: str, transaction: CreditTransaction or None)
            
        Raises:
            ValidationError: If insufficient credits
        """
        sender = interview_request.sender
        credits_required = interview_request.credits
        
        if credits_required <= 0:
            logger.warning(f"Interview {interview_request.uuid_id} has no credits specified")
            return False, "No credits specified for this interview", None
        
        # Get balance
        try:
            balance = CreditBalance.objects.select_for_update().get(user=sender)
        except CreditBalance.DoesNotExist:
            raise ValidationError(f"User {sender.email} has no credit balance")
        
        # Check sufficient funds
        if not balance.can_afford(credits_required):
            raise ValidationError(
                f"Insufficient credits. Required: {credits_required}, Available: {balance.balance}"
            )
        
        # Move credits to escrow
        balance.balance -= credits_required
        balance.escrow_balance += credits_required
        balance.total_spent += credits_required
        balance.save(update_fields=['balance', 'escrow_balance', 'total_spent', 'updated_at'])
        
        # Create transaction record
        txn = CreditTransaction.objects.create(
            user=sender,
            interview_request=interview_request,
            transaction_type=TransactionType.INTERVIEW_DEBIT,
            status=TransactionStatus.PENDING,  # Pending until interview completes
            amount=-credits_required,  # Negative = debit
            balance_after=balance.balance,
            description=f"Interview request with {interview_request.receiver.email}: {credits_required} credits reserved",
            metadata={
                'receiver_id': interview_request.receiver.id,
                'receiver_email': interview_request.receiver.email,
                'interview_uuid': str(interview_request.uuid_id),
                'escrow_amount': credits_required,
            },
            created_by=user or sender
        )
        
        logger.info(f"Debited {credits_required} credits from {sender.email} for interview {interview_request.uuid_id}")
        return True, f"Reserved {credits_required} credits for interview", txn
    
    # ========== CREDIT RELEASE TO TAKER (AFTER FEEDBACK) ==========
    
    @classmethod
    @transaction.atomic
    def release_credits_to_taker(cls, interview_request, feedback):
        """
        Release escrowed credits to taker after they submit mandatory feedback.
        
        This is the ONLY way takers can receive credits.
        Called automatically when InterviewerFeedback is submitted via signal.
        
        Args:
            interview_request: InterviewRequest instance
            feedback: InterviewerFeedback instance (from apps.interviews.feedback_models)
            
        Returns:
            tuple: (success: bool, message: str, taker_transaction: CreditTransaction or None)
        """
        # Import here to avoid circular import
        from apps.interviews.feedback_models import FeedbackStatus as InterviewFeedbackStatus
        
        # Validate feedback status
        if feedback.status != InterviewFeedbackStatus.SUBMITTED:
            raise ValidationError("Cannot release credits: Feedback not submitted")
        
        # Validate interview status
        valid_statuses = ['accepted', 'completed']
        if interview_request.status not in valid_statuses:
            raise ValidationError(f"Cannot release credits: Interview status '{interview_request.status}' not valid")
        
        sender = interview_request.sender
        receiver = interview_request.receiver  # Taker
        credits_amount = interview_request.credits
        
        if credits_amount <= 0:
            return False, "No credits to release", None
        
        # Get or create taker earnings
        taker_earnings, _ = TakerEarnings.objects.get_or_create(user=receiver)
        
        # Lock records for update
        try:
            sender_balance = CreditBalance.objects.select_for_update().get(user=sender)
        except CreditBalance.DoesNotExist:
            raise ValidationError(f"Sender {sender.email} has no credit balance")
        
        taker_earnings = TakerEarnings.objects.select_for_update().get(pk=taker_earnings.pk)
        
        # Find the original debit transaction
        original_txn = CreditTransaction.objects.filter(
            interview_request=interview_request,
            transaction_type=TransactionType.INTERVIEW_DEBIT,
            user=sender
        ).first()
        
        if not original_txn:
            logger.warning(f"No debit transaction found for interview {interview_request.uuid_id}")
        
        # Release credits from escrow
        if sender_balance.escrow_balance >= credits_amount:
            sender_balance.escrow_balance -= credits_amount
            sender_balance.save(update_fields=['escrow_balance', 'updated_at'])
        else:
            logger.warning(f"Escrow balance mismatch for {sender.email}: expected {credits_amount}, found {sender_balance.escrow_balance}")
        
        # Credit the taker
        taker_earnings.total_earned += credits_amount
        taker_earnings.save(update_fields=['total_earned', 'updated_at'])
        
        # Update original transaction status
        if original_txn:
            original_txn.status = TransactionStatus.COMPLETED
            original_txn.save(update_fields=['status'])
        
        # Create credit transaction for taker
        taker_txn = CreditTransaction.objects.create(
            user=receiver,
            interview_request=interview_request,
            transaction_type=TransactionType.INTERVIEW_CREDIT,
            status=TransactionStatus.COMPLETED,
            amount=credits_amount,  # Positive = credit
            balance_after=taker_earnings.total_earned,
            description=f"Interview payment from {sender.email}: {credits_amount} credits received",
            metadata={
                'sender_id': sender.id,
                'sender_email': sender.email,
                'interview_uuid': str(interview_request.uuid_id),
                'feedback_id': str(feedback.id),
            },
            related_transaction=original_txn
        )
        
        logger.info(f"Released {credits_amount} credits to taker {receiver.email} for interview {interview_request.uuid_id}")
        return True, f"Released {credits_amount} credits to interviewer", taker_txn
    
    # ========== REFUND (REJECTION/CANCELLATION) ==========
    
    @classmethod
    @transaction.atomic
    def refund_interview_credits(cls, interview_request, reason=''):
        """
        Refund escrowed credits to attender when interview is rejected or cancelled.
        
        Called when:
        - Interview is rejected by taker
        - Interview is cancelled by attender or admin
        
        Args:
            interview_request: InterviewRequest instance
            reason: Reason for refund
            
        Returns:
            tuple: (success: bool, message: str, transaction: CreditTransaction or None)
        """
        sender = interview_request.sender
        credits_amount = interview_request.credits
        
        if credits_amount <= 0:
            return False, "No credits to refund", None
        
        # Get balance
        try:
            balance = CreditBalance.objects.select_for_update().get(user=sender)
        except CreditBalance.DoesNotExist:
            logger.warning(f"No balance found for {sender.email} during refund")
            return False, "No balance found for refund", None
        
        # Find the original debit transaction
        original_txn = CreditTransaction.objects.filter(
            interview_request=interview_request,
            transaction_type=TransactionType.INTERVIEW_DEBIT,
            user=sender
        ).first()
        
        # Return credits from escrow to available balance
        escrow_to_return = min(credits_amount, balance.escrow_balance)
        balance.escrow_balance -= escrow_to_return
        balance.balance += credits_amount
        balance.total_spent -= credits_amount  # Undo the spent tracking
        balance.save(update_fields=['balance', 'escrow_balance', 'total_spent', 'updated_at'])
        
        # Update original transaction status
        if original_txn:
            original_txn.status = TransactionStatus.REFUNDED
            original_txn.save(update_fields=['status'])
        
        # Create refund transaction
        refund_reason = reason or f"Interview {interview_request.status}"
        txn = CreditTransaction.objects.create(
            user=sender,
            interview_request=interview_request,
            transaction_type=TransactionType.REFUND,
            status=TransactionStatus.COMPLETED,
            amount=credits_amount,  # Positive = credit (refund)
            balance_after=balance.balance,
            description=f"Refund for cancelled/rejected interview: {credits_amount} credits returned. Reason: {refund_reason}",
            metadata={
                'reason': refund_reason,
                'interview_uuid': str(interview_request.uuid_id),
                'interview_status': interview_request.status,
            },
            related_transaction=original_txn
        )
        
        logger.info(f"Refunded {credits_amount} credits to {sender.email} for interview {interview_request.uuid_id}")
        return True, f"Refunded {credits_amount} credits", txn
    
    # ========== QUERY HELPERS ==========
    
    @staticmethod
    def get_transaction_history(user, limit=50):
        """
        Get credit transaction history for a user.
        
        Args:
            user: User instance
            limit: Maximum number of transactions to return
            
        Returns:
            QuerySet of CreditTransaction
        """
        return CreditTransaction.objects.filter(
            user=user
        ).order_by('-created_at')[:limit]
    
    @staticmethod
    def get_pending_interviews_credits(user):
        """
        Get total credits currently in escrow for a user.
        
        Args:
            user: User instance
            
        Returns:
            int: Total credits in escrow
        """
        try:
            return user.credit_balance.escrow_balance
        except CreditBalance.DoesNotExist:
            return 0
    
    @staticmethod
    def get_taker_earnings(user):
        """
        Get taker earnings summary.
        
        Args:
            user: User instance (must be taker)
            
        Returns:
            dict with earnings summary
        """
        try:
            earnings = user.taker_earnings
            return earnings.get_earnings_summary()
        except TakerEarnings.DoesNotExist:
            return {
                'total_earned': 0,
                'pending_credits': 0,
                'interviews_completed': 0,
                'feedbacks_submitted': 0,
                'available_earnings': 0,
            }
    
    @staticmethod
    def check_can_request_interview(attender, credits_required):
        """
        Check if attender can afford an interview.
        
        Args:
            attender: User instance (attender)
            credits_required: Credits needed for the interview
            
        Returns:
            tuple: (can_afford: bool, balance: int, message: str)
        """
        try:
            balance = attender.credit_balance
            can_afford = balance.can_afford(credits_required)
            if can_afford:
                return True, balance.balance, "Sufficient credits available"
            else:
                return False, balance.balance, f"Insufficient credits. Required: {credits_required}, Available: {balance.balance}"
        except CreditBalance.DoesNotExist:
            return False, 0, "No credit balance found. Please complete signup first."
