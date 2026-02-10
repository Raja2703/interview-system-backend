# apps/credits/models.py
"""
Credit-based interview marketplace system models.

Models:
- CreditBalance: User's current credit balance (attenders only)
- CreditTransaction: Immutable audit log for all credit movements
- TakerEarnings: Track interviewer earnings

Note: Feedback is handled in apps.interviews.feedback_models.InterviewerFeedback

Credit Flow:
1. Attender signs up → +1000 initial credits
2. Attender requests interview → credits debited (held in escrow)
3. Interview completed + Taker submits feedback → credits released to taker
4. Interview rejected/cancelled → credits refunded to attender
5. Taker doesn't submit feedback → credits stay in escrow (not released)
"""

from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator
from django.core.exceptions import ValidationError
from django.utils import timezone
import uuid

User = settings.AUTH_USER_MODEL


class TransactionType:
    """Transaction type constants."""
    INITIAL_CREDIT = 'initial_credit'         # First-time signup bonus
    INTERVIEW_DEBIT = 'interview_debit'       # Credits held when requesting interview
    INTERVIEW_CREDIT = 'interview_credit'     # Credits released to taker after feedback
    REFUND = 'refund'                         # Credits returned on rejection/cancellation
    
    CHOICES = [
        (INITIAL_CREDIT, 'Initial Credit (Signup Bonus)'),
        (INTERVIEW_DEBIT, 'Interview Debit (Escrow)'),
        (INTERVIEW_CREDIT, 'Interview Credit (Taker Payout)'),
        (REFUND, 'Refund'),
    ]


class TransactionStatus:
    """Transaction status constants."""
    PENDING = 'pending'       # Transaction created but not finalized
    COMPLETED = 'completed'   # Transaction finalized successfully
    REFUNDED = 'refunded'     # Transaction reversed (refund processed)
    FAILED = 'failed'         # Transaction failed
    CANCELLED = 'cancelled'   # Transaction cancelled before completion
    
    CHOICES = [
        (PENDING, 'Pending'),
        (COMPLETED, 'Completed'),
        (REFUNDED, 'Refunded'),
        (FAILED, 'Failed'),
        (CANCELLED, 'Cancelled'),
    ]


class CreditBalance(models.Model):
    """
    User's credit balance.
    
    Only attenders have credit balances (they spend credits).
    Takers earn credits but don't have a balance (direct payout/transfer).
    
    Security:
    - Balance can never go negative
    - All changes must go through CreditService
    - Direct model updates should be avoided
    """
    
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False
    )
    
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='credit_balance'
    )
    
    # Current available balance
    balance = models.PositiveIntegerField(
        default=0,
        validators=[MinValueValidator(0)],
        help_text='Current available credit balance'
    )
    
    # Credits currently held in escrow (pending interviews)
    escrow_balance = models.PositiveIntegerField(
        default=0,
        validators=[MinValueValidator(0)],
        help_text='Credits held in escrow for pending/accepted interviews'
    )
    
    # Total credits ever received
    total_earned = models.PositiveIntegerField(
        default=0,
        help_text='Total credits ever received (including initial)'
    )
    
    # Total credits ever spent
    total_spent = models.PositiveIntegerField(
        default=0,
        help_text='Total credits ever spent on interviews'
    )
    
    # Whether user has received initial credits
    has_received_initial_credits = models.BooleanField(
        default=False,
        help_text='Whether user has received the 1000 initial signup credits'
    )
    
    # Audit timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = 'Credit Balance'
        verbose_name_plural = 'Credit Balances'
        indexes = [
            models.Index(fields=['user']),
            models.Index(fields=['balance']),
        ]
    
    def __str__(self):
        return f"{self.user.email}: {self.balance} credits (escrow: {self.escrow_balance})"
    
    @property
    def available_balance(self):
        """Get available balance (excluding escrow)."""
        return self.balance
    
    @property
    def total_balance(self):
        """Get total balance including escrow."""
        return self.balance + self.escrow_balance
    
    def can_afford(self, amount):
        """Check if user has enough available credits."""
        return self.balance >= amount
    
    def get_balance_summary(self):
        """Get balance summary for API responses."""
        return {
            'available_balance': self.balance,
            'escrow_balance': self.escrow_balance,
            'total_balance': self.total_balance,
            'total_earned': self.total_earned,
            'total_spent': self.total_spent,
            'has_received_initial_credits': self.has_received_initial_credits,
        }


class CreditTransaction(models.Model):
    """
    Immutable audit log for all credit movements.
    
    Every credit operation creates a transaction record.
    Transactions are never deleted or modified after creation.
    
    Design:
    - Positive amounts = credits IN (earning/refund)
    - Negative amounts = credits OUT (spending/debit)
    - Balance snapshots for reconciliation
    """
    
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False
    )
    
    # User this transaction belongs to
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='credit_transactions'
    )
    
    # Related interview request (if applicable)
    interview_request = models.ForeignKey(
        'interviews.InterviewRequest',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='credit_transactions'
    )
    
    # Transaction details
    transaction_type = models.CharField(
        max_length=30,
        choices=TransactionType.CHOICES
    )
    
    status = models.CharField(
        max_length=20,
        choices=TransactionStatus.CHOICES,
        default=TransactionStatus.PENDING
    )
    
    # Amount (positive = credit IN, negative = credit OUT)
    amount = models.IntegerField(
        help_text='Transaction amount (positive=credit, negative=debit)'
    )
    
    # Balance snapshot after this transaction
    balance_after = models.PositiveIntegerField(
        help_text='Balance after this transaction was applied'
    )
    
    # Free-form description
    description = models.TextField(
        blank=True,
        default='',
        help_text='Human-readable description of the transaction'
    )
    
    # Metadata (for additional context)
    metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text='Additional transaction metadata'
    )
    
    # Related transaction (for refunds, links to original transaction)
    related_transaction = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='child_transactions'
    )
    
    # Audit fields
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_credit_transactions',
        help_text='User who initiated this transaction'
    )
    
    class Meta:
        verbose_name = 'Credit Transaction'
        verbose_name_plural = 'Credit Transactions'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', '-created_at']),
            models.Index(fields=['interview_request']),
            models.Index(fields=['transaction_type', 'status']),
            models.Index(fields=['status']),
        ]
    
    def __str__(self):
        sign = '+' if self.amount >= 0 else ''
        return f"{self.user.email}: {sign}{self.amount} ({self.transaction_type}) - {self.status}"
    
    def save(self, *args, **kwargs):
        """Prevent modification of completed transactions."""
        # Note: For UUID primary keys, self.pk is set before save() due to default=uuid.uuid4
        # Use self._state.adding to correctly detect if this is a new record
        if not self._state.adding and self.pk:
            # This is an UPDATE, not a CREATE - check for amount modification
            try:
                original = CreditTransaction.objects.get(pk=self.pk)
                if original.amount != self.amount:
                    raise ValidationError("Cannot modify transaction amount after creation.")
            except CreditTransaction.DoesNotExist:
                # Record doesn't exist in DB yet, this is actually a create
                pass
        super().save(*args, **kwargs)


class TakerEarnings(models.Model):
    """
    Track taker (interviewer) earnings.
    
    Credits earned from completed interviews with feedback.
    """
    
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False
    )
    
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='taker_earnings'
    )
    
    # Total credits earned from all interviews
    total_earned = models.PositiveIntegerField(
        default=0,
        help_text='Total credits earned from interviews'
    )
    
    # Credits pending (interview completed, feedback not submitted)
    pending_credits = models.PositiveIntegerField(
        default=0,
        help_text='Credits pending feedback submission'
    )
    
    # Number of interviews conducted
    interviews_completed = models.PositiveIntegerField(
        default=0,
        help_text='Total number of interviews completed'
    )
    
    # Number of feedbacks submitted
    feedbacks_submitted = models.PositiveIntegerField(
        default=0,
        help_text='Total number of feedbacks submitted'
    )
    
    # Audit timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = 'Taker Earnings'
        verbose_name_plural = 'Taker Earnings'
    
    def __str__(self):
        return f"{self.user.email}: {self.total_earned} earned, {self.pending_credits} pending"
    
    def get_earnings_summary(self):
        """Get earnings summary for API responses."""
        return {
            'total_earned': self.total_earned,
            'pending_credits': self.pending_credits,
            'interviews_completed': self.interviews_completed,
            'feedbacks_submitted': self.feedbacks_submitted,
            'available_earnings': self.total_earned,
        }
