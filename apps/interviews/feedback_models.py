# apps/interviews/feedback_models.py
"""
InterviewerFeedback model for mandatory post-interview feedback.

This feedback is required for the taker (interviewer) to receive credits.
Each question has both a numeric rating (1-5) and a text explanation.

Design decisions:
1. Separate file to keep models organized and avoid touching existing code
2. OneToOneField ensures one feedback per interview
3. Status tracking for submission state
4. Signal hook for credit payout integration (decoupled)
"""

import uuid
from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.conf import settings


class FeedbackStatus:
    """Feedback submission status constants."""
    PENDING = 'pending'
    SUBMITTED = 'submitted'
    
    CHOICES = [
        (PENDING, 'Pending'),
        (SUBMITTED, 'Submitted'),
    ]


class InterviewerFeedback(models.Model):
    """
    Mandatory feedback from interviewer (taker) after an interview.
    
    All 4 rating+text fields are required for submission.
    Credits are released to taker only after successful feedback submission.
    
    Linked to InterviewRequest via OneToOneField to ensure uniqueness.
    """
    
    # Primary key
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False
    )
    
    # Relationships
    interview_request = models.OneToOneField(
        'interviews.InterviewRequest',
        on_delete=models.CASCADE,
        related_name='interviewer_feedback',
        help_text='The interview this feedback belongs to'
    )
    
    interviewer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='submitted_feedbacks',
        help_text='The taker who submitted this feedback'
    )
    
    # Status tracking
    status = models.CharField(
        max_length=20,
        choices=FeedbackStatus.CHOICES,
        default=FeedbackStatus.PENDING,
        db_index=True,
        help_text='Current submission status'
    )
    
    # ==================== FEEDBACK QUESTIONS ====================
    # Each question has a rating (1-5) and a text explanation
    
    # Q1: Problem Understanding
    problem_understanding_rating = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)],
        null=True,
        blank=True,
        help_text='Rating 1-5: How well did the candidate understand the problem?'
    )
    problem_understanding_text = models.TextField(
        blank=True,
        default='',
        help_text='Explanation of problem understanding assessment'
    )
    
    # Q2: Solution Approach
    solution_approach_rating = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)],
        null=True,
        blank=True,
        help_text='Rating 1-5: How effective was the solution approach?'
    )
    solution_approach_text = models.TextField(
        blank=True,
        default='',
        help_text='Explanation of solution approach assessment'
    )
    
    # Q3: Implementation Skill
    implementation_skill_rating = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)],
        null=True,
        blank=True,
        help_text='Rating 1-5: How well did candidate implement the solution?'
    )
    implementation_skill_text = models.TextField(
        blank=True,
        default='',
        help_text='Explanation of implementation skill assessment'
    )
    
    # Q4: Communication
    communication_rating = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)],
        null=True,
        blank=True,
        help_text='Rating 1-5: How well did the candidate communicate?'
    )
    communication_text = models.TextField(
        blank=True,
        default='',
        help_text='Explanation of communication assessment'
    )
    
    # Overall Feedback (required text)
    overall_feedback = models.TextField(
        blank=True,
        default='',
        help_text='Overall feedback and final thoughts (required for submission)'
    )
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    submitted_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text='Timestamp when feedback was submitted'
    )
    
    class Meta:
        db_table = 'interviews_interviewer_feedback'
        verbose_name = 'Interviewer Feedback'
        verbose_name_plural = 'Interviewer Feedbacks'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', 'created_at']),
            models.Index(fields=['interviewer', 'status']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['interview_request', 'interviewer'],
                name='unique_interviewer_feedback'
            )
        ]
    
    def __str__(self):
        return f"Feedback for {self.interview_request.uuid_id} by {self.interviewer.email}"
    
    # ==================== VALIDATION ====================
    
    def is_complete(self) -> bool:
        """
        Check if all required fields are filled.
        
        All 4 questions require both rating AND text.
        Overall feedback text is also required.
        """
        # Check all ratings are present
        ratings_complete = all([
            self.problem_understanding_rating is not None,
            self.solution_approach_rating is not None,
            self.implementation_skill_rating is not None,
            self.communication_rating is not None,
        ])
        
        # Check all text fields are non-empty
        texts_complete = all([
            bool(self.problem_understanding_text.strip()),
            bool(self.solution_approach_text.strip()),
            bool(self.implementation_skill_text.strip()),
            bool(self.communication_text.strip()),
        ])
        
        # Check overall feedback is present
        overall_complete = bool(self.overall_feedback.strip())
        
        return ratings_complete and texts_complete and overall_complete
    
    def get_missing_fields(self) -> list:
        """Return list of missing/incomplete fields."""
        missing = []
        
        if self.problem_understanding_rating is None:
            missing.append('problem_understanding_rating')
        if not self.problem_understanding_text.strip():
            missing.append('problem_understanding_text')
            
        if self.solution_approach_rating is None:
            missing.append('solution_approach_rating')
        if not self.solution_approach_text.strip():
            missing.append('solution_approach_text')
            
        if self.implementation_skill_rating is None:
            missing.append('implementation_skill_rating')
        if not self.implementation_skill_text.strip():
            missing.append('implementation_skill_text')
            
        if self.communication_rating is None:
            missing.append('communication_rating')
        if not self.communication_text.strip():
            missing.append('communication_text')
            
        if not self.overall_feedback.strip():
            missing.append('overall_feedback')
            
        return missing
    
    @property
    def average_rating(self) -> float:
        """Calculate average of all ratings."""
        ratings = [
            self.problem_understanding_rating,
            self.solution_approach_rating,
            self.implementation_skill_rating,
            self.communication_rating,
        ]
        valid_ratings = [r for r in ratings if r is not None]
        if not valid_ratings:
            return 0.0
        return sum(valid_ratings) / len(valid_ratings)
    
    # ==================== SUBMISSION ====================
    
    def submit(self) -> 'InterviewerFeedback':
        """
        Submit the feedback after validation.
        
        Raises:
            ValidationError: If feedback is incomplete or already submitted
        """
        # Check not already submitted
        if self.status == FeedbackStatus.SUBMITTED:
            raise ValidationError("Feedback has already been submitted")
        
        # Check interview status is valid
        interview = self.interview_request
        valid_statuses = ['accepted', 'completed']
        if interview.status not in valid_statuses:
            raise ValidationError(
                f"Cannot submit feedback for interview with status '{interview.status}'. "
                f"Interview must be {' or '.join(valid_statuses)}."
            )
        
        # Check all fields are complete
        if not self.is_complete():
            missing = self.get_missing_fields()
            raise ValidationError(
                f"Cannot submit incomplete feedback. Missing fields: {', '.join(missing)}"
            )
        
        # Mark as submitted
        self.status = FeedbackStatus.SUBMITTED
        self.submitted_at = timezone.now()
        self.save(update_fields=['status', 'submitted_at', 'updated_at'])
        
        # Trigger credit payout signal (decoupled from credit logic)
        from .feedback_signals import feedback_submitted
        feedback_submitted.send(
            sender=self.__class__,
            feedback=self,
            interview_request=self.interview_request,
            interviewer=self.interviewer
        )
        
        return self
    
    def clean(self):
        """Model-level validation."""
        super().clean()
        
        # Ensure interviewer is the taker (receiver) of the interview
        if self.interview_request_id and self.interviewer_id:
            if self.interviewer != self.interview_request.receiver:
                raise ValidationError(
                    "Only the interviewer (taker) can submit feedback for this interview"
                )
    
    def save(self, *args, **kwargs):
        """Override save to run validation."""
        self.full_clean()
        super().save(*args, **kwargs)


class CandidateFeedback(models.Model):
    """
    Optional feedback from candidate (attender) about the interviewer.
    
    All fields are optional - candidates can rate their experience.
    This feedback does NOT affect credit flow.
    
    Linked to InterviewRequest via OneToOneField to ensure one feedback per interview.
    """
    
    # Primary key
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False
    )
    
    # Relationships
    interview_request = models.OneToOneField(
        'interviews.InterviewRequest',
        on_delete=models.CASCADE,
        related_name='candidate_feedback',
        help_text='The interview this feedback belongs to'
    )
    
    candidate = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='given_candidate_feedbacks',
        help_text='The attender who submitted this feedback'
    )
    
    # ==================== OPTIONAL RATING QUESTIONS (1-5) ====================
    
    # Q1: Overall Experience
    overall_experience_rating = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)],
        null=True,
        blank=True,
        help_text='Rating 1-5: How was your overall interview experience?'
    )
    
    # Q2: Interviewer Professionalism
    professionalism_rating = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)],
        null=True,
        blank=True,
        help_text='Rating 1-5: How professional was the interviewer?'
    )
    
    # Q3: Question Clarity
    question_clarity_rating = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)],
        null=True,
        blank=True,
        help_text='Rating 1-5: How clear were the interview questions?'
    )
    
    # Q4: Feedback Quality (if interviewer provided feedback)
    feedback_quality_rating = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)],
        null=True,
        blank=True,
        help_text='Rating 1-5: How helpful was the feedback you received?'
    )
    
    # ==================== OPTIONAL TEXT & BOOLEAN ====================
    
    # Comments
    comments = models.TextField(
        blank=True,
        default='',
        help_text='Additional comments about your interview experience (optional)'
    )
    
    # Would recommend
    would_recommend = models.BooleanField(
        null=True,
        blank=True,
        help_text='Would you recommend this interviewer to others?'
    )
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'interviews_candidate_feedback'
        verbose_name = 'Candidate Feedback'
        verbose_name_plural = 'Candidate Feedbacks'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['candidate', 'created_at']),
        ]
    
    def __str__(self):
        return f"Feedback for {self.interview_request.uuid_id} by {self.candidate.email}"
    
    @property
    def average_rating(self) -> float:
        """Calculate average of all provided ratings."""
        ratings = [
            self.overall_experience_rating,
            self.professionalism_rating,
            self.question_clarity_rating,
            self.feedback_quality_rating,
        ]
        valid_ratings = [r for r in ratings if r is not None]
        if not valid_ratings:
            return 0.0
        return sum(valid_ratings) / len(valid_ratings)
    
    @property
    def has_any_rating(self) -> bool:
        """Check if at least one rating was provided."""
        return any([
            self.overall_experience_rating is not None,
            self.professionalism_rating is not None,
            self.question_clarity_rating is not None,
            self.feedback_quality_rating is not None,
        ])
    
    def clean(self):
        """Model-level validation."""
        super().clean()
        
        # Ensure candidate is the sender (attender) of the interview
        if self.interview_request_id and self.candidate_id:
            if self.candidate != self.interview_request.sender:
                raise ValidationError(
                    "Only the candidate (attender) can submit feedback for this interview"
                )
    
    def save(self, *args, **kwargs):
        """Override save to run validation."""
        self.full_clean()
        super().save(*args, **kwargs)
