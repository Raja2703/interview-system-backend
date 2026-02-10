# apps/profiles/models.py
from django.conf import settings
from django.db import models
import uuid
User = settings.AUTH_USER_MODEL


class Role(models.Model):
    """
    Role model - clean and reusable.
    Represents the available roles in the system.
    """
    ATTENDER = 'attender'
    TAKER = 'taker'
    
    ROLE_CHOICES = [
        (ATTENDER, 'Interview Attender'),
        (TAKER, 'Interview Taker'),
    ]
    
    name = models.CharField(max_length=20, choices=ROLE_CHOICES, unique=True)
    description = models.TextField(blank=True, default='')
    permissions = models.JSONField(default=dict, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['name']
    
    def __str__(self):
        return self.get_name_display()
    
    @classmethod
    def get_or_create_role(cls, role_name):
        """Get or create a role by name."""
        descriptions = {
            cls.ATTENDER: 'Can attend interviews and send interview requests.',
            cls.TAKER: 'Can conduct interviews and receive interview requests.',
        }
        role, created = cls.objects.get_or_create(
            name=role_name,
            defaults={'description': descriptions.get(role_name, '')}
        )
        return role


class UserProfile(models.Model):
    """
    User profile with multi-role support and common onboarding fields.
    A user can have multiple roles (attender, taker, or both).
    
    Contains common onboarding fields required for ALL users:
    - Mobile number
    - Bio
    - Designation
    - Years of experience
    - Available time slots
    """
    # Legacy choices - kept for reference during migration
    ROLE_CHOICES = (
        ('attender', 'Interview Attender'),
        ('taker', 'Interview Taker'),
    )

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    
    # ========== MULTI-ROLE SUPPORT ==========
    roles = models.ManyToManyField(
        Role, 
        blank=True, 
        related_name='profiles',
        help_text='User can have multiple roles (attender, taker, or both)'
    )
    
    # ========== DEPRECATED FIELDS (kept for migration safety) ==========
    role = models.CharField(
        max_length=20, 
        choices=ROLE_CHOICES, 
        null=True, 
        blank=True,
        help_text='DEPRECATED: Use roles ManyToMany field instead'
    )
    new_role = models.ForeignKey(
        Role, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='user_profiles_deprecated',
        help_text='DEPRECATED: Use roles ManyToMany field instead'
    )

    # ========== OAUTH PROVIDER INFO ==========
    oauth_provider = models.CharField(max_length=50, blank=True)
    profile_picture_url = models.URLField(blank=True)
    linkedin_id = models.CharField(max_length=255, null=True, blank=True)
    linkedin_email = models.EmailField(
        null=True,
        blank=True,
        help_text='Email address from LinkedIn OAuth (may differ from user email)'
    )
    linkedin_profile_url = models.URLField(null=True, blank=True)

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")

    # ✅ Public UUID (API-safe)
    public_id = models.UUIDField(
        default=uuid.uuid4,
        editable=False,
        null=True,          
        blank=True,         
        db_index=True
    )

    # ========== COMMON ONBOARDING FIELDS (Required for ALL users) ==========
    # Name (user's full name for display)
    name = models.CharField(
        max_length=100,
        blank=True,
        help_text='User\'s full name for display'
    )
    
    # Phone prefix (country code)
    phone_prefix = models.CharField(
        max_length=10,
        blank=True,
        default='',
        help_text='Phone number country code prefix (e.g., +91, +1, +44)'
    )
    
    # Mobile number
    mobile_number = models.CharField(
        max_length=20, 
        blank=True,
        help_text='Mobile number without country code (e.g., 9876543210)'
    )
    
    # Bio
    bio = models.TextField(
        blank=True,
        help_text='Brief professional bio'
    )
    
    # Designation (current job title)
    designation = models.CharField(
        max_length=100, 
        blank=True,
        help_text='Current job title/designation'
    )
    
    # Years of experience
    experience_years = models.PositiveIntegerField(
        default=0,
        help_text='Total years of professional experience'
    )
    
    # Available time slots (JSON array)
    # Format: [{"day": "monday", "start_time": "09:00", "end_time": "17:00"}, ...]
    available_time_slots = models.JSONField(
        default=list,
        blank=True,
        help_text='Available time slots for interviews in JSON format'
    )
    
    # Company name (common onboarding field for ALL roles)
    company = models.CharField(
        max_length=150,
        blank=True,
        help_text='Current company/organization name'
    )
    
    # ========== LEGACY FIELDS (kept for backward compatibility) ==========
    current_position = models.CharField(max_length=100, blank=True)  # Use designation instead


    # ========== ONBOARDING STATUS FIELDS ==========
    onboarding_completed = models.BooleanField(default=False)
    onboarding_steps_completed = models.JSONField(
        default=dict,
        blank=True,
        help_text='Tracks completion of each onboarding section: {"common": True, "interviewer": True, "interviewee": False}'
    )
    
    # ========== VERIFICATION FIELDS (for LinkedIn Expert System) ==========
    VERIFIED_VIA_CHOICES = (
        ('linkedin', 'LinkedIn'),
        ('admin', 'Admin Manual Verification'),
    )
    
    is_verified_user = models.BooleanField(
        default=False,
        db_index=True,
        help_text='Whether user is a verified expert (via LinkedIn or admin)'
    )
    
    verified_via = models.CharField(
        max_length=20,
        choices=VERIFIED_VIA_CHOICES,
        null=True,
        blank=True,
        help_text='How the user was verified: linkedin, admin, or null'
    )
    
    verified_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text='When the user was verified'
    )
    
    verified_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='verified_users',
        help_text='Admin who verified this user (if verified_via=admin)'
    )
    
    verification_notes = models.TextField(
        blank=True,
        default='',
        help_text='Admin notes about verification'
    )
    
    # LinkedIn data stored from OAuth (for verification matching)
    linkedin_full_name = models.CharField(
        max_length=200,
        blank=True,
        default='',
        help_text='Full name from LinkedIn profile'
    )
    
    linkedin_headline = models.CharField(
        max_length=300,
        blank=True,
        default='',
        help_text='Headline from LinkedIn profile'
    )
    
    linkedin_company = models.CharField(
        max_length=200,
        blank=True,
        default='',
        help_text='Company from LinkedIn profile'
    )
    
    linkedin_experience_years = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text='Years of experience from LinkedIn profile'
    )
    
    # ========== LEGACY INTERVIEWER FIELDS (DEPRECATED - use InterviewerProfile) ==========
    expertise_areas = models.JSONField(
        default=list,
        blank=True,
        help_text='DEPRECATED: Use InterviewerProfile.expertise_areas instead'
    )
    interviewing_experience_years = models.PositiveIntegerField(
        default=0,
        help_text='DEPRECATED: Use InterviewerProfile instead'
    )
    
    # ========== LEGACY INTERVIEWEE FIELDS (DEPRECATED - use IntervieweeProfile) ==========
    career_goals = models.TextField(
        blank=True,
        help_text='DEPRECATED: Use IntervieweeProfile.career_goal instead'
    )
    preferred_interview_domains = models.JSONField(
        default=list,
        blank=True,
        help_text='DEPRECATED: Use IntervieweeProfile instead'
    )
    resume_metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text='DEPRECATED: Use IntervieweeProfile instead'
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        roles_display = self.get_role_names() or ['No Role']
        return f"{self.user} ({', '.join(roles_display)})"
    
    # ========== MULTI-ROLE HELPER METHODS ==========
    
    def has_role(self, role_name):
        """Check if user has a specific role."""
        return self.roles.filter(name=role_name, is_active=True).exists()
    
    def has_any_role(self):
        """Check if user has at least one role assigned."""
        return self.roles.filter(is_active=True).exists()
    
    def get_role_names(self):
        """Get list of role names for the user."""
        return list(self.roles.filter(is_active=True).values_list('name', flat=True))
    
    def get_roles(self):
        """Get queryset of active Role objects for the user."""
        return self.roles.filter(is_active=True)
    
    def add_roles(self, role_names):
        """Add roles to user without removing existing roles."""
        for role_name in role_names:
            if role_name in [Role.ATTENDER, Role.TAKER]:
                role = Role.get_or_create_role(role_name)
                self.roles.add(role)
    
    def set_roles(self, role_names):
        """Set user's roles, replacing any existing roles."""
        self.roles.clear()
        self.add_roles(role_names)
    
    def remove_role(self, role_name):
        """Remove a specific role from user."""
        self.roles.filter(name=role_name).delete()
    
    def is_attender(self):
        """Check if user has attender role."""
        return self.has_role(Role.ATTENDER)
    
    def is_taker(self):
        """Check if user has taker role."""
        return self.has_role(Role.TAKER)
    
    def is_both(self):
        """Check if user has both attender and taker roles."""
        return self.is_attender() and self.is_taker()
    
    def get_effective_role(self):
        """DEPRECATED: Get first role for backward compatibility."""
        role_names = self.get_role_names()
        if role_names:
            return role_names[0]
        if self.new_role:
            return self.new_role.name
        return self.role
    
    # ========== COMMON ONBOARDING VALIDATION ==========
    
    def is_common_onboarding_complete(self):
        """
        Check if common onboarding fields are complete (data-driven validation).
        Required fields: name, mobile_number, bio, designation, experience_years, available_time_slots
        Note: company is optional
        """
        has_name = bool(self.name and self.name.strip())
        has_mobile = bool(self.mobile_number and self.mobile_number.strip())
        has_bio = bool(self.bio and len(self.bio.strip()) >= 10)
        has_designation = bool(self.designation and self.designation.strip())
        has_experience = self.experience_years >= 0  # 0 is valid
        has_time_slots = bool(self.available_time_slots and len(self.available_time_slots) > 0)
        
        return all([has_name, has_mobile, has_bio, has_designation, has_time_slots])
    
    # ========== ONBOARDING HELPER METHODS ==========
    
    def get_required_onboarding_steps(self):
        """Get list of required onboarding steps based on user's roles."""
        required_steps = ['common']
        
        if self.is_taker():
            required_steps.append('interviewer')
        
        if self.is_attender():
            required_steps.append('interviewee')
        
        return required_steps
    
    def get_pending_onboarding_steps(self):
        """Get list of onboarding steps that are not yet completed (data-driven)."""
        required_steps = self.get_required_onboarding_steps()
        pending = []
        
        for step in required_steps:
            if step == 'common':
                if not self.is_common_onboarding_complete():
                    pending.append(step)
            elif step == 'interviewer':
                if not self.is_interviewer_onboarding_complete():
                    pending.append(step)
            elif step == 'interviewee':
                if not self.is_interviewee_onboarding_complete():
                    pending.append(step)
        
        return pending
    
    def is_interviewer_onboarding_complete(self):
        """Check if interviewer onboarding is complete (data-driven)."""
        try:
            interviewer_profile = self.interviewer_profile
            return interviewer_profile.is_complete()
        except InterviewerProfile.DoesNotExist:
            return False
    
    def is_interviewee_onboarding_complete(self):
        """Check if interviewee onboarding is complete (data-driven)."""
        try:
            interviewee_profile = self.interviewee_profile
            return interviewee_profile.is_complete()
        except IntervieweeProfile.DoesNotExist:
            return False
    
    def is_onboarding_required(self):
        """Check if user still has pending onboarding steps."""
        if not self.has_any_role():
            return False
        
        if self.onboarding_completed:
            # Double-check with data-driven validation
            pending = self.get_pending_onboarding_steps()
            if pending:
                # Reset the flag if data is incomplete
                self.onboarding_completed = False
                self.save(update_fields=['onboarding_completed'])
                return True
            return False
        
        return len(self.get_pending_onboarding_steps()) > 0
    
    def calculate_onboarding_completion(self):
        """Calculate and update the overall onboarding_completed status (data-driven)."""
        pending_steps = self.get_pending_onboarding_steps()
        is_complete = len(pending_steps) == 0
        
        if is_complete != self.onboarding_completed:
            self.onboarding_completed = is_complete
            self.save(update_fields=['onboarding_completed'])
        
        # Also update steps_completed tracking
        if self.onboarding_steps_completed is None:
            self.onboarding_steps_completed = {}
        
        for step in self.get_required_onboarding_steps():
            self.onboarding_steps_completed[step] = step not in pending_steps
        
        self.save(update_fields=['onboarding_steps_completed'])
        
        return is_complete
    
    def update_onboarding_step(self, step_name, completed=True):
        """Update the completion status of a specific onboarding step."""
        if self.onboarding_steps_completed is None:
            self.onboarding_steps_completed = {}
        
        self.onboarding_steps_completed[step_name] = completed
        self.save(update_fields=['onboarding_steps_completed'])
        
        # Recalculate overall completion (data-driven)
        self.calculate_onboarding_completion()
    
    def get_onboarding_status(self):
        """Get comprehensive onboarding status for API responses."""
        required_steps = self.get_required_onboarding_steps()
        pending_steps = self.get_pending_onboarding_steps()
        
        completed_steps_dict = {}
        for step in required_steps:
            completed_steps_dict[step] = step not in pending_steps
        
        return {
            'onboarding_completed': len(pending_steps) == 0,
            'required_steps': required_steps,
            'completed_steps': completed_steps_dict,
            'pending_steps': pending_steps,
            'progress_percentage': int((len(required_steps) - len(pending_steps)) / max(len(required_steps), 1) * 100)
        }
    
    # ========== VERIFICATION HELPER METHODS ==========
    
    def verify_user(self, verified_via, verified_by=None, notes=''):
        """
        Mark user as verified.
        
        Args:
            verified_via: 'linkedin' or 'admin'
            verified_by: User who verified (for admin verification)
            notes: Optional verification notes
        """
        from django.utils import timezone
        
        self.is_verified_user = True
        self.verified_via = verified_via
        self.verified_at = timezone.now()
        self.verified_by = verified_by
        self.verification_notes = notes
        self.save(update_fields=[
            'is_verified_user', 'verified_via', 'verified_at',
            'verified_by', 'verification_notes'
        ])
    
    def unverify_user(self, admin_user=None, notes=''):
        """
        Remove user verification status.
        
        Args:
            admin_user: Admin who removed verification
            notes: Reason for removal
        """
        from django.utils import timezone
        
        old_verified_via = self.verified_via
        self.is_verified_user = False
        self.verified_via = None
        self.verified_at = None
        self.verified_by = None
        self.verification_notes = f"Unverified by admin: {notes}" if notes else ''
        self.save(update_fields=[
            'is_verified_user', 'verified_via', 'verified_at',
            'verified_by', 'verification_notes'
        ])
    
    def get_verification_status(self):
        """Get verification status for API responses."""
        return {
            'is_verified': self.is_verified_user,
            'verified_via': self.verified_via,
            'verified_at': self.verified_at.isoformat() if self.verified_at else None,
            'verification_message': self._get_verification_message(),
        }
    
    def _get_verification_message(self):
        """Get user-facing verification message."""
        if self.is_verified_user:
            if self.verified_via == 'linkedin':
                return "Verified via LinkedIn"
            elif self.verified_via == 'admin':
                return "Verified by platform admin"
            return "Verified user"
        else:
            if self.oauth_provider == 'linkedin':
                return "LinkedIn connected but not yet verified as expert"
            return "Verify your profile by signing in once via LinkedIn"
    
    def update_linkedin_data(self, linkedin_data):
        """
        Update LinkedIn-sourced fields from OAuth data.
        
        Args:
            linkedin_data: dict with LinkedIn profile data
        """
        if linkedin_data.get('full_name'):
            self.linkedin_full_name = linkedin_data['full_name'][:200]
        if linkedin_data.get('headline'):
            self.linkedin_headline = linkedin_data['headline'][:300]
        if linkedin_data.get('company'):
            self.linkedin_company = linkedin_data['company'][:200]
        if linkedin_data.get('experience_years') is not None:
            self.linkedin_experience_years = linkedin_data['experience_years']
        if linkedin_data.get('profile_url'):
            self.linkedin_profile_url = linkedin_data['profile_url']
        
        self.save(update_fields=[
            'linkedin_full_name', 'linkedin_headline', 'linkedin_company',
            'linkedin_experience_years', 'linkedin_profile_url'
        ])


class IntervieweeProfile(models.Model):
    """
    Interview Attender (Candidate) specific onboarding profile.
    OneToOne with UserProfile for users with 'attender' role.
    
    Fields:
    - Skills with proficiency levels
    - Target role
    - Preferred interview language
    - Career goal (finding jobs / switching jobs)
    """
    
    SKILL_LEVEL_CHOICES = [
        ('beginner', 'Beginner'),
        ('intermediate', 'Intermediate'),
        ('expert', 'Expert'),
    ]
    
    CAREER_GOAL_CHOICES = [
        ('finding_jobs', 'Finding Jobs'),
        ('switching_jobs', 'Switching Jobs'),
    ]
    
    user_profile = models.OneToOneField(
        UserProfile,
        on_delete=models.CASCADE,
        related_name='interviewee_profile'
    )
    
    # Skills with levels
    # Format: [{"skill": "Python", "level": "expert"}, {"skill": "JavaScript", "level": "intermediate"}]
    skills = models.JSONField(
        default=list,
        blank=True,
        help_text='Skills with proficiency levels: [{"skill": "Python", "level": "expert"}]'
    )
    
    # Target role
    target_role = models.CharField(
        max_length=100,
        blank=True,
        help_text='Target job role (e.g., "Senior Software Engineer")'
    )
    
    # Preferred interview language
    preferred_interview_language = models.CharField(
        max_length=50,
        blank=True,
        help_text='Preferred language for conducting interviews (e.g., "English", "Hindi")'
    )
    
    # Career goal
    career_goal = models.CharField(
        max_length=20,
        choices=CAREER_GOAL_CHOICES,
        blank=True,
        help_text='Career goal: finding jobs or switching jobs'
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = 'Interviewee Profile'
        verbose_name_plural = 'Interviewee Profiles'
    
    def __str__(self):
        return f"Interviewee: {self.user_profile.user.email}"
    
    def is_complete(self):
        """
        Check if interviewee onboarding is complete (data-driven validation).
        Required: skills (at least 1), target_role, preferred_interview_language, career_goal
        """
        has_skills = bool(self.skills and len(self.skills) >= 1)
        has_target_role = bool(self.target_role and self.target_role.strip())
        has_language = bool(self.preferred_interview_language and self.preferred_interview_language.strip())
        has_career_goal = bool(self.career_goal and self.career_goal.strip())
        
        return all([has_skills, has_target_role, has_language, has_career_goal])
    
    def get_skills_by_level(self, level):
        """Get skills filtered by proficiency level."""
        if not self.skills:
            return []
        return [s['skill'] for s in self.skills if s.get('level') == level]


class InterviewerProfile(models.Model):
    """
    Interview Taker (Interviewer) specific onboarding profile.
    OneToOne with UserProfile for users with 'taker' role.
    
    Fields:
    - Expertise areas with proficiency levels
    - Credits per interview
    """
    
    EXPERTISE_LEVEL_CHOICES = [
        ('beginner', 'Beginner'),
        ('intermediate', 'Intermediate'),
        ('expert', 'Expert'),
    ]
    
    user_profile = models.OneToOneField(
        UserProfile,
        on_delete=models.CASCADE,
        related_name='interviewer_profile'
    )
    
    # Expertise areas with levels
    # Format: [{"area": "System Design", "level": "expert"}, {"area": "Python", "level": "intermediate"}]
    expertise_areas = models.JSONField(
        default=list,
        blank=True,
        help_text='Expertise areas with levels: [{"area": "System Design", "level": "expert"}]'
    )
    
    # Interviewing experience (years)
    interviewing_experience_years = models.PositiveIntegerField(
        default=0,
        help_text='Years of experience conducting interviews'
    )
    
    # Credits per interview
    credits_per_interview = models.PositiveIntegerField(
        default=0,
        help_text='Number of credits charged per interview session'
    )
    
    # LinkedIn profile URL (specific to interviewers)
    linkedin_profile_url = models.URLField(
        blank=True,
        help_text='LinkedIn profile URL for verification'
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = 'Interviewer Profile'
        verbose_name_plural = 'Interviewer Profiles'
    
    def __str__(self):
        return f"Interviewer: {self.user_profile.user.email}"
    
    def is_complete(self):
        """
        Check if interviewer onboarding is complete (data-driven validation).
        Required: expertise_areas (at least 1), interviewing_experience_years >= 0, 
                  credits_per_interview > 0, linkedin_profile_url (optional but recommended)
        """
        has_expertise = bool(self.expertise_areas and len(self.expertise_areas) >= 1)
        has_interviewing_exp = self.interviewing_experience_years >= 0  # 0 is valid for new interviewers
        has_credits = self.credits_per_interview > 0
        
        return all([has_expertise, has_credits])
    
    def get_expertise_by_level(self, level):
        """Get expertise areas filtered by proficiency level."""
        if not self.expertise_areas:
            return []
        return [e['area'] for e in self.expertise_areas if e.get('level') == level]
