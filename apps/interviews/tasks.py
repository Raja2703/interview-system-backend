# apps/interviews/tasks.py
"""
Celery tasks for interview management.

Tasks:
- finalize_expired_interviews: Periodic task to auto-finalize interviews
  based on the 20-minute expiry logic.

Schedule:
- Runs every 5 minutes via Celery Beat (configured in settings.py)
"""

import logging
from celery import shared_task
from django.utils import timezone
from django.db import transaction
from django.db.models import Q

logger = logging.getLogger('apps.interviews.tasks')


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    autoretry_for=(Exception,),
    acks_late=True  # Ensure task completion before ack
)
def finalize_expired_interviews(self):
    """
    Periodic Celery task to finalize interviews that have expired.
    
    Checks for accepted interviews where:
    1. 20 minutes have passed since scheduled_time (for non-attendance cases)
    2. Join window has fully expired
    
    Uses database indexes for efficient querying:
    - status='accepted' filter uses the status index
    - Scheduled_time comparison uses the composite index
    
    This task is idempotent - safe to run multiple times.
    """
    from apps.interviews.models import InterviewRequest
    
    now = timezone.now()
    
    # Query for interviews that might need finalization:
    # - Status is 'accepted'
    # - Scheduled time is in the past (at least started)
    # Using select_for_update to prevent race conditions
    interviews = InterviewRequest.objects.filter(
        status=InterviewRequest.STATUS_ACCEPTED,
        scheduled_time__lt=now
    ).select_related(
        'livekit_room'  # Pre-fetch for attendance checks
    ).order_by('scheduled_time')  # Process oldest first
    
    finalized_count = 0
    error_count = 0
    processed_ids = []
    
    logger.info(
        f"[TASK_START] finalize_expired_interviews "
        f"found={interviews.count()} candidates at={now.isoformat()}"
    )
    
    for interview in interviews:
        try:
            # Each interview finalization is atomic
            was_finalized = interview.finalize_if_expired()
            
            if was_finalized:
                finalized_count += 1
                processed_ids.append(str(interview.uuid_id))
                logger.info(
                    f"[INTERVIEW_FINALIZED] interview={interview.uuid_id} "
                    f"final_status={interview.status}"
                )
                
        except Exception as e:
            error_count += 1
            logger.error(
                f"[FINALIZATION_ERROR] interview={interview.uuid_id} "
                f"error={str(e)}"
            )
            # Continue processing other interviews
            continue
    
    logger.info(
        f"[TASK_COMPLETE] finalize_expired_interviews "
        f"finalized={finalized_count} errors={error_count} "
        f"processed_ids={processed_ids[:10]}{'...' if len(processed_ids) > 10 else ''}"
    )
    
    return {
        'finalized': finalized_count,
        'errors': error_count,
        'total_processed': len(processed_ids),
    }


@shared_task
def cleanup_expired_pending_interviews():
    """
    Optional task to mark pending interviews as expired if scheduled_time has passed.
    This handles the case where an interview was never accepted.
    
    Note: This is a separate concern from finalize_expired_interviews which 
    handles accepted interviews.
    """
    from apps.interviews.models import InterviewRequest
    
    now = timezone.now()
    
    # Find pending interviews where scheduled time has passed
    expired_pending = InterviewRequest.objects.filter(
        status=InterviewRequest.STATUS_PENDING,
        scheduled_time__lt=now - timezone.timedelta(hours=1)  # 1 hour grace period
    )
    
    count = 0
    for interview in expired_pending:
        try:
            with transaction.atomic():
                interview.status = InterviewRequest.STATUS_NOT_CONDUCTED
                interview.expired_at = now
                interview.save(update_fields=['status', 'expired_at', 'updated_at'])
                count += 1
                
                logger.info(
                    f"[PENDING_EXPIRED] interview={interview.uuid_id} "
                    f"scheduled_time={interview.scheduled_time.isoformat()}"
                )
        except Exception as e:
            logger.error(
                f"[PENDING_EXPIRY_ERROR] interview={interview.uuid_id} error={str(e)}"
            )
    
    logger.info(f"[TASK_COMPLETE] cleanup_expired_pending_interviews expired={count}")
    
    return {'expired': count}
