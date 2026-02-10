# apps/interviews/feedback_serializers.py
"""
DRF Serializers for InterviewerFeedback API.

Validates all required fields and provides clear error messages.
"""

from rest_framework import serializers
from .feedback_models import InterviewerFeedback, FeedbackStatus


class InterviewerFeedbackSerializer(serializers.ModelSerializer):
    """
    Serializer for viewing interviewer feedback.
    
    Read-only serializer for retrieving feedback data.
    """
    
    interview_uuid = serializers.SerializerMethodField()
    interviewer_email = serializers.EmailField(source='interviewer.email', read_only=True)
    average_rating = serializers.FloatField(read_only=True)
    is_complete = serializers.BooleanField(read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    
    class Meta:
        model = InterviewerFeedback
        fields = [
            'id',
            'interview_uuid',
            'interviewer_email',
            'status',
            'status_display',
            # Q1: Problem Understanding
            'problem_understanding_rating',
            'problem_understanding_text',
            # Q2: Solution Approach
            'solution_approach_rating',
            'solution_approach_text',
            # Q3: Implementation Skill
            'implementation_skill_rating',
            'implementation_skill_text',
            # Q4: Communication
            'communication_rating',
            'communication_text',
            # Overall
            'overall_feedback',
            # Computed
            'average_rating',
            'is_complete',
            # Timestamps
            'submitted_at',
            'created_at',
            'updated_at',
        ]
        read_only_fields = fields
    
    def get_interview_uuid(self, obj):
        return str(obj.interview_request.uuid_id)


class InterviewerFeedbackSubmitSerializer(serializers.Serializer):
    """
    Serializer for submitting interviewer feedback.
    
    All 4 questions require both a rating (1-5) and text explanation.
    Overall feedback text is also required.
    
    Validation:
    - All ratings must be between 1-5
    - All text fields must be non-empty
    - overall_feedback is required
    """
    
    # Q1: Problem Understanding
    problem_understanding_rating = serializers.IntegerField(
        min_value=1, max_value=5,
        help_text='Rating 1-5: How well did the candidate understand the problem?'
    )
    problem_understanding_text = serializers.CharField(
        min_length=10,
        help_text='Explanation of problem understanding assessment (min 10 chars)'
    )
    
    # Q2: Solution Approach
    solution_approach_rating = serializers.IntegerField(
        min_value=1, max_value=5,
        help_text='Rating 1-5: How effective was the solution approach?'
    )
    solution_approach_text = serializers.CharField(
        min_length=10,
        help_text='Explanation of solution approach assessment (min 10 chars)'
    )
    
    # Q3: Implementation Skill
    implementation_skill_rating = serializers.IntegerField(
        min_value=1, max_value=5,
        help_text='Rating 1-5: How well did candidate implement the solution?'
    )
    implementation_skill_text = serializers.CharField(
        min_length=10,
        help_text='Explanation of implementation skill assessment (min 10 chars)'
    )
    
    # Q4: Communication
    communication_rating = serializers.IntegerField(
        min_value=1, max_value=5,
        help_text='Rating 1-5: How well did the candidate communicate?'
    )
    communication_text = serializers.CharField(
        min_length=10,
        help_text='Explanation of communication assessment (min 10 chars)'
    )
    
    # Overall Feedback
    overall_feedback = serializers.CharField(
        min_length=20,
        help_text='Overall feedback and final thoughts (min 20 chars, required)'
    )
    
    """def validate(self, data):
        return data"""
    def validate(self, data):
        request = self.context['request']
        interview = self.context['interview_request']
        interviewer = request.user

        if hasattr(interview, 'interviewer_feedback'):
            raise serializers.ValidationError(
                "Feedback has already been submitted for this interview."
            )

        return data




class InterviewerFeedbackResponseSerializer(serializers.Serializer):
    """Response serializer for successful feedback submission."""
    
    detail = serializers.CharField()
    feedback = InterviewerFeedbackSerializer()
    credits_pending = serializers.IntegerField(
        help_text='Credits pending for payout (hook triggered)'
    )


# ==================== CANDIDATE FEEDBACK SERIALIZERS ====================

class CandidateFeedbackSerializer(serializers.ModelSerializer):
    """
    Serializer for viewing candidate feedback.
    
    Read-only serializer for retrieving optional candidate feedback.
    """
    
    interview_uuid = serializers.SerializerMethodField()
    candidate_email = serializers.EmailField(source='candidate.email', read_only=True)
    average_rating = serializers.FloatField(read_only=True)
    has_any_rating = serializers.BooleanField(read_only=True)
    
    class Meta:
        from .feedback_models import CandidateFeedback
        model = CandidateFeedback
        fields = [
            'id',
            'interview_uuid',
            'candidate_email',
            # Ratings (all optional, 1-5)
            'overall_experience_rating',
            'professionalism_rating',
            'question_clarity_rating',
            'feedback_quality_rating',
            # Text & Boolean
            'comments',
            'would_recommend',
            # Computed
            'average_rating',
            'has_any_rating',
            # Timestamps
            'created_at',
            'updated_at',
        ]
        read_only_fields = fields
    
    def get_interview_uuid(self, obj):
        return str(obj.interview_request.uuid_id)


class CandidateFeedbackSubmitSerializer(serializers.Serializer):
    """
    Serializer for submitting candidate feedback.
    
    ALL fields are optional - candidates can submit as little or as much as they want.
    
    Validation:
    - Ratings must be between 1-5 (if provided)
    - At least one field should have a value
    """
    
    # Optional Ratings (1-5)
    overall_experience_rating = serializers.IntegerField(
        required=False, min_value=1, max_value=5, allow_null=True,
        help_text='Rating 1-5: How was your overall interview experience?'
    )
    professionalism_rating = serializers.IntegerField(
        required=False, min_value=1, max_value=5, allow_null=True,
        help_text='Rating 1-5: How professional was the interviewer?'
    )
    question_clarity_rating = serializers.IntegerField(
        required=False, min_value=1, max_value=5, allow_null=True,
        help_text='Rating 1-5: How clear were the interview questions?'
    )
    feedback_quality_rating = serializers.IntegerField(
        required=False, min_value=1, max_value=5, allow_null=True,
        help_text='Rating 1-5: How helpful was the feedback you received?'
    )
    
    # Optional Text & Boolean
    comments = serializers.CharField(
        required=False, allow_blank=True,
        help_text='Additional comments about your interview experience (optional)'
    )
    would_recommend = serializers.BooleanField(
        required=False, allow_null=True,
        help_text='Would you recommend this interviewer to others?'
    )
    
    def validate(self, data):
        """Ensure at least one field is provided."""
        has_any_data = any([
            data.get('overall_experience_rating') is not None,
            data.get('professionalism_rating') is not None,
            data.get('question_clarity_rating') is not None,
            data.get('feedback_quality_rating') is not None,
            data.get('comments', '').strip(),
            data.get('would_recommend') is not None,
        ])
        
        if not has_any_data:
            raise serializers.ValidationError(
                "At least one field (rating, comments, or recommendation) must be provided."
            )
        
        return data


class CandidateFeedbackResponseSerializer(serializers.Serializer):
    """Response serializer for successful candidate feedback submission."""
    
    detail = serializers.CharField()
    feedback = CandidateFeedbackSerializer()

