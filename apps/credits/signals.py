# apps/credits/signals.py
"""
Django signals for credit system integration.

Signals handle:
1. Initial credits on first login (for attenders)
2. Credit debit when interview request is created
3. Credit refund when interview is rejected/cancelled
4. Credit release when feedback is submitted (via new InterviewerFeedback)

These signals work in conjunction with the credit service
to maintain consistency without modifying existing code.
"""

import logging
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.contrib.auth.signals import user_logged_in
from django.db import transaction as db_transaction

from apps.interviews.models import InterviewRequest
# Import the signal from the NEW feedback system in interviews app
from apps.interviews.feedback_signals import feedback_submitted
from .models import CreditBalance, TakerEarnings
from .services import CreditService

logger = logging.getLogger(__name__)


# ========== FIRST LOGIN INITIAL CREDITS ==========

@receiver(user_logged_in)
def award_initial_credits_on_first_login(sender, user, request, **kwargs):
    """
    Award initial credits when an attender logs in for the first time.
    
    Triggered by Django's built-in user_logged_in signal.
    Works for both OAuth and regular login.
    """
    try:
        # Check if user has attender role
        if not hasattr(user, 'profile'):
            logger.debug(f"User {user.email} has no profile, skipping initial credits")
            return
        
        if not user.profile.is_attender():
            logger.debug(f"User {user.email} is not an attender, skipping initial credits")
            return
        
        # Award initial credits (service handles duplicate checks)
        success, message, txn = CreditService.award_initial_credits(user)
        
        if success:
            logger.info(f"First login credits awarded to {user.email}: {message}")
        else:
            logger.debug(f"Initial credits not awarded to {user.email}: {message}")
            
    except Exception as e:
        # Don't fail login on credit errors
        logger.error(f"Error awarding initial credits to {user.email}: {str(e)}")


# ========== INTERVIEW REQUEST SIGNALS ==========

# Track previous status to detect changes
_interview_status_cache = {}


@receiver(pre_save, sender=InterviewRequest)
def cache_interview_previous_status(sender, instance, **kwargs):
    """Cache the previous status before save to detect changes."""
    if instance.pk:
        try:
            old_instance = InterviewRequest.objects.get(pk=instance.pk)
            _interview_status_cache[instance.pk] = old_instance.status
        except InterviewRequest.DoesNotExist:
            _interview_status_cache[instance.pk] = None
    else:
        _interview_status_cache[instance.pk] = None


@receiver(post_save, sender=InterviewRequest)
def handle_interview_status_change(sender, instance, created, **kwargs):
    """
    Handle credit operations based on interview status changes.
    
    - Created (pending): Debit credits from attender
    - Rejected/Cancelled: Refund credits to attender
    - Completed: Track pending earnings for taker (credits released after feedback)
    """
    interview = instance
    previous_status = _interview_status_cache.get(instance.pk)
    current_status = interview.status
    
    # Clean up cache
    if instance.pk in _interview_status_cache:
        del _interview_status_cache[instance.pk]
    
    try:
        if created:
            # ===== NEW INTERVIEW REQUEST =====
            # Debit credits from attender (move to escrow)
            if interview.credits > 0:
                try:
                    with db_transaction.atomic():
                        success, message, txn = CreditService.debit_for_interview_request(interview)
                        if success:
                            logger.info(f"Credits debited for new interview {interview.uuid_id}: {message}")
                        else:
                            logger.warning(f"No credits debited for interview {interview.uuid_id}: {message}")
                except Exception as e:
                    logger.error(f"Failed to debit credits for interview {interview.uuid_id}: {str(e)}")
            
            return  # Exit after handling creation
        
        # ===== STATUS TRANSITIONS =====
        
        if previous_status == current_status:
            return  # No status change
        
        logger.debug(f"Interview {interview.uuid_id} status changed: {previous_status} -> {current_status}")
        
        # Handle REJECTION
        if current_status == InterviewRequest.STATUS_REJECTED:
            if interview.credits > 0:
                try:
                    with db_transaction.atomic():
                        success, message, txn = CreditService.refund_interview_credits(
                            interview,
                            reason=interview.rejection_reason or 'Interview rejected by interviewer'
                        )
                        if success:
                            logger.info(f"Credits refunded for rejected interview {interview.uuid_id}: {message}")
                except Exception as e:
                    logger.error(f"Failed to refund credits for rejected interview {interview.uuid_id}: {str(e)}")
        
        # Handle CANCELLATION
        elif current_status == InterviewRequest.STATUS_CANCELLED:
            if interview.credits > 0:
                try:
                    with db_transaction.atomic():
                        success, message, txn = CreditService.refund_interview_credits(
                            interview,
                            reason=interview.rejection_reason or 'Interview cancelled'
                        )
                        if success:
                            logger.info(f"Credits refunded for cancelled interview {interview.uuid_id}: {message}")
                except Exception as e:
                    logger.error(f"Failed to refund credits for cancelled interview {interview.uuid_id}: {str(e)}")
        
        # Handle COMPLETION
        elif current_status == InterviewRequest.STATUS_COMPLETED:
            # Update taker earnings (pending credits - will be released after feedback)
            try:
                taker = interview.receiver
                taker_earnings, _ = TakerEarnings.objects.get_or_create(user=taker)
                taker_earnings.interviews_completed += 1
                if interview.credits > 0:
                    taker_earnings.pending_credits += interview.credits
                taker_earnings.save(update_fields=['interviews_completed', 'pending_credits', 'updated_at'])
                logger.info(f"Taker earnings updated for completed interview {interview.uuid_id}")
                
            except Exception as e:
                logger.error(f"Failed to update taker earnings for interview {interview.uuid_id}: {str(e)}")
        
        # Handle NOT ATTENDED (manually marked by taker)
        elif current_status == InterviewRequest.STATUS_NOT_ATTENDED:
            # Refund credits since interview didn't happen
            if interview.credits > 0:
                try:
                    with db_transaction.atomic():
                        success, message, txn = CreditService.refund_interview_credits(
                            interview,
                            reason='Interview not attended'
                        )
                        if success:
                            logger.info(f"Credits refunded for not attended interview {interview.uuid_id}: {message}")
                except Exception as e:
                    logger.error(f"Failed to refund credits for not attended interview {interview.uuid_id}: {str(e)}")
        
        # Handle NOT CONDUCTED (auto-expired due to non-attendance)
        elif current_status == InterviewRequest.STATUS_NOT_CONDUCTED:
            # Refund credits since interview was never conducted
            if interview.credits > 0:
                try:
                    with db_transaction.atomic():
                        success, message, txn = CreditService.refund_interview_credits(
                            interview,
                            reason='Interview not conducted - participant(s) did not join'
                        )
                        if success:
                            logger.info(f"Credits refunded for not conducted interview {interview.uuid_id}: {message}")
                except Exception as e:
                    logger.error(f"Failed to refund credits for not conducted interview {interview.uuid_id}: {str(e)}")
    
    except Exception as e:
        logger.error(f"Error handling interview status change for {interview.uuid_id}: {str(e)}")


# ========== NEW FEEDBACK SUBMISSION SIGNAL ==========

@receiver(feedback_submitted)
def handle_interviewer_feedback_submission(sender, feedback, interview_request, interviewer, **kwargs):
    """
    Handle credit release when the NEW InterviewerFeedback is submitted.
    
    This signal is dispatched from apps.interviews.feedback_models.InterviewerFeedback.submit()
    Credits are released from escrow to taker upon successful feedback submission.
    """
    try:
        with db_transaction.atomic():
            # Release credits from escrow to taker
            success, message, txn = CreditService.release_credits_to_taker(
                interview_request, 
                feedback
            )
            
            if success:
                logger.info(
                    f"Credits released to taker {interviewer.email} "
                    f"for interview {interview_request.uuid_id}: {message}"
                )
                
                # Update taker earnings
                taker_earnings, _ = TakerEarnings.objects.get_or_create(user=interviewer)
                if interview_request.credits > 0 and taker_earnings.pending_credits >= interview_request.credits:
                    taker_earnings.pending_credits -= interview_request.credits
                taker_earnings.feedbacks_submitted += 1
                taker_earnings.save(update_fields=['pending_credits', 'feedbacks_submitted', 'updated_at'])
            else:
                logger.warning(f"Credits not released for interview {interview_request.uuid_id}: {message}")
                
    except Exception as e:
        logger.error(
            f"Error releasing credits for interview {interview_request.uuid_id}: {str(e)}"
        )


# ========== ROLE CHANGE SIGNAL ==========

def handle_attender_role_assignment(user):
    """
    Award initial credits when a user is assigned attender role.
    
    This function should be called from the role assignment logic.
    """
    try:
        # Check if user already has credits
        CreditService.award_initial_credits(user)
    except Exception as e:
        logger.error(f"Error awarding initial credits on role assignment for {user.email}: {str(e)}")
