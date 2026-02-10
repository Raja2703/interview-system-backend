# apps/notifications/signals.py
"""
Signals for automatic notification creation on interview events.

Connects to InterviewRequest model status changes and triggers
appropriate notifications via the NotificationService.
"""
import logging
from django.db.models.signals import post_save
from django.dispatch import receiver

logger = logging.getLogger(__name__)

# Note: Direct signal-based notification is not used here because 
# we need more control over when notifications are sent (e.g., after
# the transaction is complete). Instead, notifications are triggered
# directly in the interview API views/model methods.
#
# This file is kept for potential future use with more complex signal
# requirements or for other notification triggers.

# Example signal handler (commented out - notifications are handled in views):
#
# @receiver(post_save, sender='interviews.InterviewRequest')
# def handle_interview_request_save(sender, instance, created, **kwargs):
#     """Handle interview request save events."""
#     from .services import NotificationService
#     
#     if created:
#         NotificationService.notify_interview_created(instance)
