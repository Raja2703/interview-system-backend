# apps/profiles/serializers.py
from rest_framework import serializers
from .models import UserProfile, Role, IntervieweeProfile, InterviewerProfile


class RoleSerializer(serializers.ModelSerializer):
    """Serializer for Role model."""

    class Meta:
        model = Role
        fields = ["name", "description"]
        read_only_fields = ["name", "description"]


class RoleSelectionSerializer(serializers.Serializer):
    """
    Serializer for role selection API.
    Accepts a list of roles for multi-role support.
    """

    roles = serializers.ListField(
        child=serializers.ChoiceField(choices=[Role.ATTENDER, Role.TAKER]),
        min_length=1,
        max_length=2,
        help_text='List of roles to assign. Options: "attender", "taker", or both.',
    )

    def validate_roles(self, value):
        """Validate and deduplicate role list."""
        seen = set()
        unique_roles = []
        for role in value:
            if role not in seen:
                seen.add(role)
                unique_roles.append(role)

        if not unique_roles:
            raise serializers.ValidationError("At least one role must be selected.")

        return unique_roles


class IntervieweeProfileSerializer(serializers.ModelSerializer):
    """Serializer for IntervieweeProfile model."""

    class Meta:
        model = IntervieweeProfile
        fields = [
            "skills",
            "target_role",
            "preferred_interview_language",
            "career_goal",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at"]


class InterviewerProfileSerializer(serializers.ModelSerializer):
    """Serializer for InterviewerProfile model."""

    class Meta:
        model = InterviewerProfile
        fields = [
            "expertise_areas",
            "interviewing_experience_years",
            "credits_per_interview",
            "linkedin_profile_url",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at"]


class UserProfileSerializer(serializers.ModelSerializer):
    """
    User profile serializer with multi-role support.
    Returns roles as a list of role names.
    """

    roles = serializers.SerializerMethodField()
    role = serializers.SerializerMethodField()  # Backward compatibility
    interviewee_profile = IntervieweeProfileSerializer(read_only=True)
    interviewer_profile = InterviewerProfileSerializer(read_only=True)
    onboarding_progress = serializers.SerializerMethodField()
    is_verified_user = serializers.BooleanField(read_only=True)

    class Meta:
        model = UserProfile
        fields = [
            "roles",
            "role",  # DEPRECATED
            "name",
            "phone_prefix",  # NEW
            "mobile_number",
            "bio",
            "designation",
            "company",  # NEW - common onboarding field
            "experience_years",
            "available_time_slots",
            "current_position",  # DEPRECATED - use designation
            "linkedin_profile_url",
            "onboarding_completed",
            "onboarding_progress",
            "interviewee_profile",
            "interviewer_profile",
            "public_id",
            "is_verified_user",
        ]

    def get_roles(self, obj):
        """Return list of role names."""
        return obj.get_role_names()

    def get_role(self, obj):
        """DEPRECATED: Return first role for backward compatibility."""
        return obj.get_effective_role()

    def get_onboarding_progress(self, obj):
        status = obj.get_onboarding_status()
        return status.get("progress_percentage", 0)


class ProfileListSerializer(serializers.ModelSerializer):
    """
    Read-only serializer for listing user profiles.
    Used in /api/profiles/attenders/, /api/profiles/takers/, /api/profiles/both/
    """

    roles = serializers.SerializerMethodField()
    user_email = serializers.EmailField(source="user.email", read_only=True)
    #user_id = serializers.UUIDField(source="public_id", read_only=True)
    user_username = serializers.CharField(source="user.username", read_only=True)
    interviewee_profile = IntervieweeProfileSerializer(read_only=True)
    interviewer_profile = InterviewerProfileSerializer(read_only=True)
    verification_status = serializers.SerializerMethodField()
    public_id = serializers.UUIDField(read_only=True)

    class Meta:
        model = UserProfile
        fields = [
            "id",
            "user_id",
            "public_id",
            "user_email",
            "user_username",
            "roles",
            "name",
            "phone_prefix",
            "bio",
            "designation",
            "company",
            "experience_years",
            "available_time_slots",
            "linkedin_profile_url",
            "onboarding_completed",
            "profile_picture_url",
            # Verification fields
            "is_verified_user",
            "verified_via",
            "verification_status",
            # Nested profiles
            "interviewee_profile",
            "interviewer_profile",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields  # All fields are read-only for listing

    def get_roles(self, obj):
        """Return list of role names."""
        return obj.get_role_names()

    def get_verification_status(self, obj):
        """Return verification status details."""
        return obj.get_verification_status()


class ProfileUpdateSerializer(serializers.Serializer):
    """
    Nested serializer for profile updates with role-based validation.

    Expected Structure:
    {
        "common": { "name": "...", ... },
        "interviewer": { "expertise_areas": [...], ... },
        "interviewee": { "skills": [...], ... }
    }
    """

    # 1. Accept the Full List of Desired Roles (e.g., ["taker", "attender"])
    roles = serializers.ListField(
        child=serializers.ChoiceField(choices=[Role.ATTENDER, Role.TAKER]),
        required=False,
    )

    # Use DictField to accept nested objects and validate them manually with partial=True
    common = serializers.DictField(required=False)
    interviewer = serializers.DictField(required=False)
    interviewee = serializers.DictField(required=False)

    add_roles = serializers.ListField(
        child=serializers.ChoiceField(choices=[Role.ATTENDER, Role.TAKER]),
        required=False,
    )
    remove_roles = serializers.ListField(
        child=serializers.ChoiceField(choices=[Role.ATTENDER, Role.TAKER]),
        required=False,
    )

    def validate_common(self, value):
        """Validate common fields using CommonOnboardingSerializer."""
        # partial=True allows updating single fields like just 'name'
        serializer = CommonOnboardingSerializer(data=value, partial=True)
        if not serializer.is_valid():
            raise serializers.ValidationError(serializer.errors)
        return serializer.validated_data

    def validate_interviewer(self, value):
        """Validate interviewer fields using InterviewerOnboardingSerializer."""
        serializer = InterviewerOnboardingSerializer(data=value, partial=True)
        if not serializer.is_valid():
            raise serializers.ValidationError(serializer.errors)
        return serializer.validated_data

    def validate_interviewee(self, value):
        """Validate interviewee fields using IntervieweeOnboardingSerializer."""
        serializer = IntervieweeOnboardingSerializer(data=value, partial=True)
        if not serializer.is_valid():
            raise serializers.ValidationError(serializer.errors)
        return serializer.validated_data

    def validate(self, attrs):
        """
        Enforce role-based permissions.
        """
        user = self.context["request"].user

        # Ensure profile exists
        try:
            profile = user.profile
        except UserProfile.DoesNotExist:
            raise serializers.ValidationError("UserProfile does not exist.")

        # --- ROLE VALIDATION ---
        current_db_roles = set(profile.get_role_names())

        # Determine the "Effective Roles" for this request.
        if "roles" in attrs:
            # Full replacement
            effective_roles = set(attrs["roles"])
        else:
            # Start with existing roles
            effective_roles = current_db_roles.copy()

        # Apply additions
        if "add_roles" in attrs:
            effective_roles.update(attrs["add_roles"])

        # Apply removals
        if "remove_roles" in attrs:
            effective_roles.difference_update(attrs["remove_roles"])

        # Ensure at least one role remains
        if not effective_roles:
            raise serializers.ValidationError(
                {"roles": "User must have at least one role after updates."}
            )

        # 1. Taker Validation
        if "interviewer" in attrs and attrs["interviewer"]:
            if Role.TAKER not in effective_roles:
                raise serializers.ValidationError(
                    {
                        "interviewer": "You must select the 'Interviewer' role to update this profile."
                    }
                )

        # 2. Attender Validation
        if "interviewee" in attrs and attrs["interviewee"]:
            if Role.ATTENDER not in effective_roles:
                raise serializers.ValidationError(
                    {
                        "interviewee": "You must select the 'Candidate' role to update this profile."
                    }
                )

        # return attrs
        return super().validate(attrs)

    def update(self, instance, validated_data):
        """
        Handle the nested update logic.
        """
        old_roles = set(instance.get_role_names())

        # Calculate new roles set
        new_roles_set = old_roles.copy()
        roles_updated = False

        if "roles" in validated_data:
            new_roles_set = set(validated_data.pop("roles"))
            roles_updated = True
        
        if "add_roles" in validated_data:
            to_add = set(validated_data.pop("add_roles"))
            new_roles_set.update(to_add)
            roles_updated = True
            
        if "remove_roles" in validated_data:
            to_remove = set(validated_data.pop("remove_roles"))
            new_roles_set.difference_update(to_remove)
            roles_updated = True

        # Apply role changes if needed
        if roles_updated and new_roles_set != old_roles:
            # Check for at least one role again (safety net)
            if not new_roles_set:
                 raise serializers.ValidationError("User must have at least one role.")
            
            # Update DB
            db_roles = Role.objects.filter(name__in=new_roles_set)
            instance.roles.set(db_roles)
            
            # Award initial credits if attender role was newly added
            if Role.ATTENDER in new_roles_set and Role.ATTENDER not in old_roles:
                try:
                    from apps.credits.signals import handle_attender_role_assignment
                    handle_attender_role_assignment(instance.user)
                    import logging
                    logger = logging.getLogger(__name__)
                    logger.info(f"Triggered initial credits award for new attender {instance.user.email} via profile update")
                except Exception as e:
                    import logging
                    logger = logging.getLogger(__name__)
                    logger.error(f"Error awarding initial credits via profile update: {str(e)}")

        # 1. Update Common Fields (UserProfile)
        if "common" in validated_data:
            common_data = validated_data["common"]

            # Map fields to instance
            fields_map = {
                "name": "name",
                "phone_prefix": "phone_prefix",
                "mobile_number": "mobile_number",
                "bio": "bio",
                "designation": "designation",
                "company": "company",
                "experience_years": "experience_years",
                "available_time_slots": "available_time_slots",
            }

            for data_key, model_field in fields_map.items():
                if data_key in common_data:
                    setattr(instance, model_field, common_data[data_key])

            # Sync legacy field
            if "designation" in common_data:
                instance.current_position = common_data["designation"]

            instance.save()

        # 2. Update Interviewer Fields (InterviewerProfile)
        if "interviewer" in validated_data:
            interviewer_data = validated_data["interviewer"]
            # Get or create nested profile
            interviewer_profile, _ = InterviewerProfile.objects.get_or_create(
                user_profile=instance
            )

            # Map fields
            if "expertise_areas" in interviewer_data:
                interviewer_profile.expertise_areas = interviewer_data[
                    "expertise_areas"
                ]
            if "interviewing_experience_years" in interviewer_data:
                interviewer_profile.interviewing_experience_years = interviewer_data[
                    "interviewing_experience_years"
                ]
            if "credits_per_interview" in interviewer_data:
                interviewer_profile.credits_per_interview = interviewer_data[
                    "credits_per_interview"
                ]
            if "linkedin_profile_url" in interviewer_data:
                interviewer_profile.linkedin_profile_url = interviewer_data[
                    "linkedin_profile_url"
                ]

            interviewer_profile.save()

        # 3. Update Interviewee Fields (IntervieweeProfile)
        if "interviewee" in validated_data:
            interviewee_data = validated_data["interviewee"]
            # Get or create nested profile
            interviewee_profile, _ = IntervieweeProfile.objects.get_or_create(
                user_profile=instance
            )

            # Map fields
            if "skills" in interviewee_data:
                interviewee_profile.skills = interviewee_data["skills"]
            if "target_role" in interviewee_data:
                interviewee_profile.target_role = interviewee_data["target_role"]
            if "preferred_interview_language" in interviewee_data:
                interviewee_profile.preferred_interview_language = interviewee_data[
                    "preferred_interview_language"
                ]
            if "career_goal" in interviewee_data:
                interviewee_profile.career_goal = interviewee_data["career_goal"]

            interviewee_profile.save()
        # Recalculate onboarding progress (Important!)
        instance.calculate_onboarding_completion()
        current_roles = set(instance.get_role_names())

        if Role.ATTENDER in current_roles:
            from apps.credits.services import CreditService
            CreditService.award_initial_credits(instance.user)
        return instance

        


# ========== ONBOARDING SERIALIZERS ==========


class OnboardingStatusSerializer(serializers.Serializer):
    """Serializer for onboarding status response."""

    onboarding_completed = serializers.BooleanField()
    required_steps = serializers.ListField(child=serializers.CharField())
    completed_steps = serializers.DictField()
    pending_steps = serializers.ListField(child=serializers.CharField())
    progress_percentage = serializers.IntegerField()
    user_roles = serializers.ListField(child=serializers.CharField(), required=False)


class TimeSlotSerializer(serializers.Serializer):
    """Serializer for individual time slot."""

    day = serializers.ChoiceField(
        choices=[
            "monday",
            "tuesday",
            "wednesday",
            "thursday",
            "friday",
            "saturday",
            "sunday",
        ],
        help_text="Day of the week",
    )
    start_time = serializers.TimeField(
        format="%H:%M", help_text="Start time (HH:MM format)"
    )
    end_time = serializers.TimeField(
        format="%H:%M", help_text="End time (HH:MM format)"
    )

    def validate(self, data):
        """Ensure end_time is after start_time."""
        if data["end_time"] <= data["start_time"]:
            raise serializers.ValidationError("End time must be after start time.")
        return data


class CommonOnboardingSerializer(serializers.Serializer):
    """
    Serializer for common onboarding fields (all users).

    Required fields:
    - name
    - mobile_number
    - bio
    - designation
    - experience_years
    - available_time_slots
    - company
    """

    name = serializers.CharField(
        required=True, max_length=100, help_text="Your full name"
    )
    phone_prefix = serializers.CharField(
        required=False,
        max_length=10,
        default="",
        allow_blank=True,
        help_text="Phone number country code prefix (e.g., +91, +1, +44)",
    )
    mobile_number = serializers.CharField(
        required=True,
        min_length=6,
        max_length=20,
        help_text="Mobile number without country code (e.g., 9876543210)",
    )
    bio = serializers.CharField(
        required=True,
        min_length=10,
        max_length=1000,
        help_text="Brief professional bio (10-1000 characters)",
    )
    designation = serializers.CharField(
        required=True, max_length=100, help_text="Current job title/designation"
    )
    experience_years = serializers.IntegerField(
        required=True,
        min_value=0,
        max_value=50,
        help_text="Total years of professional experience",
    )
    available_time_slots = serializers.ListField(
        child=serializers.DictField(),
        required=True,
        min_length=1,
        max_length=20,
        help_text='Available time slots: [{"day": "monday", "start_time": "09:00", "end_time": "17:00"}]',
    )
    company = serializers.CharField(
        required=False,
        max_length=150,
        allow_blank=True,
        help_text="Current company/organization name (optional)",
    )

    def validate_mobile_number(self, value):
        """Validate mobile number format (without country code prefix)."""
        import re

        # Basic phone validation: allows digits, spaces, and dashes only
        # Prefix is stored separately now
        cleaned = re.sub(r"[\s\-]", "", value)
        if not re.match(r"^\d{6,15}$", cleaned):
            raise serializers.ValidationError(
                "Invalid mobile number format. Enter digits only (6-15 digits)."
            )
        return cleaned  # Return cleaned version

    def validate_available_time_slots(self, value):
        """Validate time slots structure."""
        valid_days = [
            "monday",
            "tuesday",
            "wednesday",
            "thursday",
            "friday",
            "saturday",
            "sunday",
        ]

        for i, slot in enumerate(value):
            if not isinstance(slot, dict):
                raise serializers.ValidationError(f"Time slot {i+1} must be an object.")

            if "day" not in slot:
                raise serializers.ValidationError(
                    f"Time slot {i+1} must have a 'day' field."
                )

            if slot["day"].lower() not in valid_days:
                raise serializers.ValidationError(
                    f"Time slot {i+1} has invalid day. Must be one of: {', '.join(valid_days)}"
                )

            if "start_time" not in slot or "end_time" not in slot:
                raise serializers.ValidationError(
                    f"Time slot {i+1} must have 'start_time' and 'end_time' fields."
                )

            # Normalize day to lowercase
            slot["day"] = slot["day"].lower()

        return value


class SkillSerializer(serializers.Serializer):
    """Serializer for skill with proficiency level."""

    skill = serializers.CharField(
        max_length=50, help_text='Skill name (e.g., "Python", "JavaScript")'
    )
    level = serializers.ChoiceField(
        choices=["beginner", "intermediate", "expert"],
        help_text="Proficiency level: beginner, intermediate, or expert",
    )


class IntervieweeOnboardingSerializer(serializers.Serializer):
    """
    Serializer for interviewee-specific onboarding fields.
    For users with 'attender' role (Interview Attender = Candidate).

    Required fields:
    - skills (with levels)
    - target_role
    - preferred_interview_language
    - career_goal
    """

    skills = serializers.ListField(
        child=serializers.DictField(),
        required=True,
        min_length=1,
        max_length=20,
        help_text='Skills with levels: [{"skill": "Python", "level": "expert"}]',
    )
    target_role = serializers.CharField(
        required=True,
        max_length=100,
        help_text='Target job role (e.g., "Senior Software Engineer")',
    )
    preferred_interview_language = serializers.CharField(
        required=True,
        max_length=50,
        help_text='Preferred language for interviews (e.g., "English", "Hindi")',
    )
    career_goal = serializers.ChoiceField(
        choices=["finding_jobs", "switching_jobs"],
        required=True,
        help_text="Career goal: finding_jobs or switching_jobs",
    )

    def validate_skills(self, value):
        """Validate skills structure with levels."""
        valid_levels = ["beginner", "intermediate", "expert"]

        for i, skill in enumerate(value):
            if not isinstance(skill, dict):
                raise serializers.ValidationError(f"Skill {i+1} must be an object.")

            if "skill" not in skill:
                raise serializers.ValidationError(
                    f"Skill {i+1} must have a 'skill' field."
                )

            if "level" not in skill:
                raise serializers.ValidationError(
                    f"Skill {i+1} must have a 'level' field."
                )

            if skill["level"].lower() not in valid_levels:
                raise serializers.ValidationError(
                    f"Skill {i+1} has invalid level. Must be one of: {', '.join(valid_levels)}"
                )

            # Normalize level to lowercase
            skill["level"] = skill["level"].lower()

        return value


class ExpertiseSerializer(serializers.Serializer):
    """Serializer for expertise area with proficiency level."""

    area = serializers.CharField(
        max_length=50, help_text='Expertise area (e.g., "System Design", "Python")'
    )
    level = serializers.ChoiceField(
        choices=["beginner", "intermediate", "expert"],
        help_text="Proficiency level: beginner, intermediate, or expert",
    )


class InterviewerOnboardingSerializer(serializers.Serializer):
    """
    Serializer for interviewer-specific onboarding fields.
    For users with 'taker' role (Interview Taker = Interviewer).

    Required fields:
    - expertise_areas (with levels)
    - interviewing_experience_years
    - credits_per_interview
    - linkedin_profile_url (optional)
    """

    expertise_areas = serializers.ListField(
        child=serializers.DictField(),
        required=True,
        min_length=1,
        max_length=20,
        help_text='Expertise areas with levels: [{"area": "System Design", "level": "expert"}]',
    )
    interviewing_experience_years = serializers.IntegerField(
        required=True,
        min_value=0,
        max_value=50,
        help_text="Years of experience conducting interviews",
    )
    credits_per_interview = serializers.IntegerField(
        required=True,
        min_value=1,
        max_value=10000,
        help_text="Credits charged per interview session (minimum 1)",
    )
    linkedin_profile_url = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=500,
        help_text="LinkedIn profile URL for verification (e.g., https://linkedin.com/in/username)",
    )

    def validate_linkedin_profile_url(self, value):
        """Auto-prepend https:// if URL starts with www. or linkedin.com"""
        if not value:
            return value

        value = value.strip()

        # Auto-prepend https:// if missing
        if value.startswith("www."):
            value = "https://" + value
        elif value.startswith("linkedin.com"):
            value = "https://" + value
        elif not value.startswith("http://") and not value.startswith("https://"):
            value = "https://" + value

        # Basic URL validation
        from django.core.validators import URLValidator
        from django.core.exceptions import ValidationError as DjangoValidationError

        validator = URLValidator()
        try:
            validator(value)
        except DjangoValidationError:
            raise serializers.ValidationError(
                "Enter a valid LinkedIn URL (e.g., https://linkedin.com/in/username)"
            )

        return value

    def validate_expertise_areas(self, value):
        """Validate expertise areas structure with levels."""
        valid_levels = ["beginner", "intermediate", "expert"]

        for i, expertise in enumerate(value):
            if not isinstance(expertise, dict):
                raise serializers.ValidationError(f"Expertise {i+1} must be an object.")

            if "area" not in expertise:
                raise serializers.ValidationError(
                    f"Expertise {i+1} must have an 'area' field."
                )

            if "level" not in expertise:
                raise serializers.ValidationError(
                    f"Expertise {i+1} must have a 'level' field."
                )

            if expertise["level"].lower() not in valid_levels:
                raise serializers.ValidationError(
                    f"Expertise {i+1} has invalid level. Must be one of: {', '.join(valid_levels)}"
                )

            # Normalize level to lowercase
            expertise["level"] = expertise["level"].lower()

        return value


class OnboardingStepSerializer(serializers.Serializer):
    """
    Serializer for submitting a single onboarding step.
    """

    step = serializers.ChoiceField(
        choices=["common", "interviewer", "interviewee"],
        help_text="Onboarding step to complete",
    )
    data = serializers.DictField(help_text="Step-specific data")

    def validate(self, attrs):
        """Validate step data based on step type."""
        step = attrs.get("step")
        data = attrs.get("data", {})

        if step == "common":
            serializer = CommonOnboardingSerializer(data=data)
        elif step == "interviewer":
            serializer = InterviewerOnboardingSerializer(data=data)
        elif step == "interviewee":
            serializer = IntervieweeOnboardingSerializer(data=data)
        else:
            raise serializers.ValidationError({"step": "Invalid step type"})

        if not serializer.is_valid():
            raise serializers.ValidationError({"data": serializer.errors})

        attrs["validated_step_data"] = serializer.validated_data
        return attrs


class CompleteOnboardingSerializer(serializers.Serializer):
    """
    Serializer for completing all onboarding steps at once.
    """

    common = serializers.DictField(
        required=True, help_text="Common onboarding data (required for all users)"
    )
    interviewer = serializers.DictField(
        required=False, help_text="Interviewer-specific data (required for taker role)"
    )
    interviewee = serializers.DictField(
        required=False,
        help_text="Interviewee-specific data (required for attender role)",
    )


# ========== USER DETAIL SERIALIZERS (NEW) ==========


class UserPublicProfileSerializer(serializers.ModelSerializer):
    """
    Read-only serializer for public profile view.

    Shows limited fields that are safe to expose to other users.
    Used when a normal user views another user's profile.
    """

    roles = serializers.SerializerMethodField()
    user_id = serializers.UUIDField(source="public_id", read_only=True)
    interviewee_profile = IntervieweeProfileSerializer(read_only=True)
    interviewer_profile = InterviewerProfileSerializer(read_only=True)

    class Meta:
        model = UserProfile
        fields = [
            "user_id",
            "roles",
            "name",
            "bio",
            "designation",
            "experience_years",
            "linkedin_profile_url",
            "onboarding_completed",
            "profile_picture_url",
            "interviewee_profile",
            "interviewer_profile",
            "created_at",
        ]
        read_only_fields = fields

    def get_roles(self, obj):
        """Return list of role names."""
        return obj.get_role_names()


class UserFullProfileSerializer(serializers.ModelSerializer):
    """
    Full profile serializer for admin view.

    Shows all fields including sensitive data.
    Used when an admin views any user's profile.
    """

    roles = serializers.SerializerMethodField()
    # user_id = serializers.IntegerField(source='user.id', read_only=True)
    user_id = serializers.UUIDField(source="public_id", read_only=True)
    user_email = serializers.EmailField(source="user.email", read_only=True)
    user_username = serializers.CharField(source="user.username", read_only=True)
    is_active = serializers.BooleanField(source="user.is_active", read_only=True)
    is_staff = serializers.BooleanField(source="user.is_staff", read_only=True)
    is_superuser = serializers.BooleanField(source="user.is_superuser", read_only=True)
    date_joined = serializers.DateTimeField(source="user.date_joined", read_only=True)
    last_login = serializers.DateTimeField(source="user.last_login", read_only=True)
    interviewee_profile = IntervieweeProfileSerializer(read_only=True)
    interviewer_profile = InterviewerProfileSerializer(read_only=True)
    onboarding_status = serializers.SerializerMethodField()

    class Meta:
        model = UserProfile
        fields = [
            "id",
            "user_id",
            "user_email",
            "user_username",
            "is_active",
            "is_staff",
            "is_superuser",
            "date_joined",
            "last_login",
            "roles",
            "name",
            "phone_prefix",
            "mobile_number",
            "bio",
            "designation",
            "company",
            "experience_years",
            "available_time_slots",
            "linkedin_profile_url",
            "onboarding_completed",
            "onboarding_status",
            "profile_picture_url",
            "oauth_provider",
            "linkedin_id",
            "interviewee_profile",
            "interviewer_profile",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    def get_roles(self, obj):
        """Return list of role names."""
        return obj.get_role_names()

    def get_onboarding_status(self, obj):
        """Return full onboarding status."""
        return obj.get_onboarding_status()


class AdminUserUpdateSerializer(serializers.ModelSerializer):
    """
    Serializer for admin to update any user's profile.
    Supports updating most profile fields.
    """

    class Meta:
        model = UserProfile
        fields = [
            "name",
            "phone_prefix",
            "mobile_number",
            "bio",
            "designation",
            "company",
            "experience_years",
            "available_time_slots",
            "linkedin_profile_url",
            "profile_picture_url",
            "onboarding_completed",
        ]
        extra_kwargs = {
            "name": {"required": False},
            "phone_prefix": {"required": False},
            "mobile_number": {"required": False},
            "bio": {"required": False},
            "designation": {"required": False},
            "company": {"required": False},
            "experience_years": {"required": False},
            "available_time_slots": {"required": False},
            "linkedin_profile_url": {"required": False},
            "profile_picture_url": {"required": False},
            "onboarding_completed": {"required": False},
        }


# ========== ADMIN VERIFICATION SERIALIZERS ==========


class AdminVerifyUserSerializer(serializers.Serializer):
    """
    Serializer for admin to manually verify a user.
    """

    notes = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=500,
        help_text="Optional verification notes",
    )


class AdminUnverifyUserSerializer(serializers.Serializer):
    """
    Serializer for admin to remove user verification.
    """

    reason = serializers.CharField(
        required=True, max_length=500, help_text="Reason for removing verification"
    )


class UserVerificationSerializer(serializers.ModelSerializer):
    """
    Serializer for viewing user verification details (admin only).
    """

    verified_by_email = serializers.EmailField(
        source="verified_by.email", read_only=True, allow_null=True
    )
    verification_status = serializers.SerializerMethodField()

    class Meta:
        model = UserProfile
        fields = [
            "is_verified_user",
            "verified_via",
            "verified_at",
            "verified_by_email",
            "verification_notes",
            "verification_status",
            # LinkedIn data
            "linkedin_id",
            "linkedin_profile_url",
            "linkedin_full_name",
            "linkedin_headline",
            "linkedin_company",
            "linkedin_experience_years",
        ]
        read_only_fields = fields

    def get_verification_status(self, obj):
        return obj.get_verification_status()
