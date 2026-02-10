# apps/interviews/feedback_signals.py
"""
Signals for interviewer feedback system.

Provides a clean hook for credit payout integration without
coupling the feedback logic to the credit system.

Usage in credit app:
    from apps.interviews.feedback_signals import feedback_submitted
    
    @receiver(feedback_submitted)
    def handle_feedback_submission(sender, feedback, interview_request, interviewer, **kwargs):
        # Release credits to interviewer
        CreditService.release_credits_to_taker(interview_request, feedback)
"""

import django.dispatch

# Signal dispatched when interviewer feedback is successfully submitted
# Receivers can use this to trigger credit payout, notifications, etc.
feedback_submitted = django.dispatch.Signal()
# Provides: feedback (InterviewerFeedback), interview_request, interviewer
