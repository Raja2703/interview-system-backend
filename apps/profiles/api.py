# apps/profiles/api.py

import json
import logging
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required
from django.db import models
from django.db.models import (
    Case,
    When,
    Value,
    IntegerField,
    BooleanField,
    Q,
    Exists,
    OuterRef,
    Count,
)
from django.db.models.functions import Coalesce
from rest_framework.views import APIView
from rest_framework.generics import ListAPIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.decorators import api_view, permission_classes

# from rest_framework.pagination import PageNumberPagination
from rest_framework import status
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi
from .serializers import (
    UserProfileSerializer,
    RoleSelectionSerializer,
    RoleSerializer,
    CommonOnboardingSerializer,
    InterviewerOnboardingSerializer,
    IntervieweeOnboardingSerializer,
    OnboardingStepSerializer,
    ProfileListSerializer,
    ProfileUpdateSerializer,
    UserPublicProfileSerializer,
    UserFullProfileSerializer,
    AdminUserUpdateSerializer,
)
from .models import UserProfile, Role, IntervieweeProfile, InterviewerProfile
from apps.interviews.permissions import IsAdmin, IsAdminOrSelf
from django.contrib.auth import get_user_model

User = get_user_model()


logger = logging.getLogger(__name__)

# Available roles configuration
AVAILABLE_ROLES = [
    {
        "name": "attender",
        "display_name": "Interview Attender",
        "description": "Can attend interviews and send interview requests.",
    },
    {
        "name": "taker",
        "display_name": "Interview Taker",
        "description": "Can conduct interviews and receive interview requests.",
    },
]


class ProfileAPI(APIView):
    """API endpoint for retrieving user profile (GET only)."""

    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        tags=["Profile"],
        operation_id="profile_get",
        operation_summary="Get User Profile",
        operation_description="Retrieve the authenticated user's complete profile information including roles, onboarding status, and role-specific profiles.",
        responses={200: UserProfileSerializer},
    )
    def get(self, request):
        """Get current user's profile."""
        serializer = UserProfileSerializer(request.user.profile)
        return Response(serializer.data)


class ProfileUpdateAPI(APIView):
    """
    Dedicated API endpoint for updating user profile.

    Endpoint: PUT /api/profile/update/

    This endpoint allows authenticated users to update their profile information.
    Supports partial updates - you only need to include the fields you want to update.

    The request body is organized into three sections:
    - common: Basic profile fields (available to all users)
    - interviewer: Interviewer-specific fields (requires 'taker' role)
    - interviewee: Interviewee-specific fields (requires 'attender' role)
    """

    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        tags=["Profile"],
        operation_id="profile_update",
        operation_summary="Update User Profile",
        operation_description="""
## Update User Profile

Update the authenticated user's profile information. Supports **partial updates**.

### Role Management
You can add or remove roles using `add_roles` and `remove_roles`.
- `add_roles`: List of roles to add (e.g., `["taker"]`)
- `remove_roles`: List of roles to remove (e.g., `["attender"]`)

---

### Request Structure

The request body is organized into sections:

| Section | Description | Availability |
|---------|-------------|--------------|
| `common` | Basic profile information | All users |
| `interviewer` | Interviewer-specific data | Users with 'taker' role only |
| `interviewee` | Interviewee-specific data | Users with 'attender' role only |

---

### Common Fields (All Users)

| Field | Type | Description | Constraints |
|-------|------|-------------|-------------|
| `name` | string | User's full display name | Max 100 characters |
| `phone_prefix` | string | Country code prefix (e.g., +91, +1) | Max 10 characters, optional |
| `mobile_number` | string | Mobile phone number without country code | 6-15 digits |
| `bio` | string | Professional bio/summary | 10-1000 characters |
| `designation` | string | Current job title/position | Max 100 characters |
| `company` | string | Current company/organization name | Max 150 characters, optional |
| `experience_years` | integer | Total years of professional experience | 0-50 |
| `available_time_slots` | array | Weekly availability schedule | 1-20 slots |

**Time Slot Format:**
```json
{
  "day": "monday",       // monday-sunday (lowercase)
  "start_time": "09:00", // HH:MM format (24-hour)
  "end_time": "17:00"    // HH:MM format (24-hour)
}
```

---

### Interviewer Fields (Taker Role Only)

| Field | Type | Description | Constraints |
|-------|------|-------------|-------------|
| `expertise_areas` | array | Areas of expertise for conducting interviews | 1-20 areas |
| `interviewing_experience_years` | integer | Years of experience as an interviewer | 0-50 |
| `credits_per_interview` | integer | Credits charged per interview session | 1-10000 |
| `linkedin_profile_url` | string | LinkedIn profile URL (for verification) | Valid URL, optional |

**Expertise Area Format:**
```json
{
  "area": "System Design",  // Expertise area name
  "level": "expert"         // beginner, intermediate, or expert
}
```

---

### Interviewee Fields (Attender Role Only)

| Field | Type | Description | Constraints |
|-------|------|-------------|-------------|
| `skills` | array | Technical/professional skills | 1-20 skills |
| `target_role` | string | Desired job role/position | Max 100 characters |
| `preferred_interview_language` | string | Language preference for interviews | Max 50 characters |
| `career_goal` | string | Current career objective | "finding_jobs" or "switching_jobs" |

**Skill Format:**
```json
{
  "skill": "Python",        // Skill name
  "level": "intermediate"   // beginner, intermediate, or expert
}
```

---

### Example: Update Common Fields Only

```json
{
  "common": {
    "name": "John Doe",
    "designation": "Senior Software Engineer",
    "bio": "Experienced backend developer with 5+ years in Python and Django"
  }
}
```

### Example: Update Interviewer Fields (Taker Role)

```json
{
  "interviewer": {
    "expertise_areas": [
      {"area": "Python", "level": "expert"},
      {"area": "System Design", "level": "intermediate"}
    ],
    "credits_per_interview": 200
  }
}
```

### Example: Full Update (Both Roles)

```json
{
  "common": {
    "name": "Jane Smith",
    "phone_prefix": "+91",
    "mobile_number": "9876543210",
    "bio": "Full-stack developer passionate about building scalable systems",
    "designation": "Tech Lead",
    "company": "Tech Corp Inc.",
    "experience_years": 8,
    "available_time_slots": [
      {"day": "monday", "start_time": "10:00", "end_time": "18:00"},
      {"day": "wednesday", "start_time": "14:00", "end_time": "20:00"}
    ]
  },
  "interviewer": {
    "expertise_areas": [
      {"area": "System Design", "level": "expert"},
      {"area": "Java", "level": "expert"}
    ],
    "interviewing_experience_years": 4,
    "credits_per_interview": 150,
    "linkedin_profile_url": "https://linkedin.com/in/janesmith"
  },
  "interviewee": {
    "skills": [
      {"skill": "React", "level": "intermediate"},
      {"skill": "Node.js", "level": "expert"}
    ],
    "target_role": "Engineering Manager",
    "preferred_interview_language": "English",
    "career_goal": "switching_jobs"
  }
}
```

---

### Error Responses

| Code | Description |
|------|-------------|
| 400 | Validation error (invalid field values) |
| 401 | Unauthorized (missing/invalid token) |
| 403 | Role permission error (trying to update fields for a role you don't have) |
""",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                "add_roles": openapi.Schema(
                    type=openapi.TYPE_ARRAY,
                    items=openapi.Schema(
                        type=openapi.TYPE_STRING, enum=["attender", "taker"]
                    ),
                    description="List of roles to add to the user.",
                    example=["taker"],
                ),
                "remove_roles": openapi.Schema(
                    type=openapi.TYPE_ARRAY,
                    items=openapi.Schema(
                        type=openapi.TYPE_STRING, enum=["attender", "taker"]
                    ),
                    description="List of roles to remove from the user.",
                    example=["attender"],
                ),
                "common": openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    description="Common profile fields available to all users",
                    properties={
                        "name": openapi.Schema(
                            type=openapi.TYPE_STRING,
                            description="Your full display name (max 100 characters)",
                            example="John Doe",
                        ),
                        "phone_prefix": openapi.Schema(
                            type=openapi.TYPE_STRING,
                            description="Country code prefix for phone number (e.g., +91, +1, +44). Optional.",
                            example="+91",
                        ),
                        "mobile_number": openapi.Schema(
                            type=openapi.TYPE_STRING,
                            description="Mobile phone number WITHOUT country code. Must be 6-15 digits.",
                            example="9876543210",
                        ),
                        "bio": openapi.Schema(
                            type=openapi.TYPE_STRING,
                            description="Professional bio/summary describing your experience and skills. Must be 10-1000 characters.",
                            example="Senior software engineer with 5+ years of experience in Python, Django, and cloud technologies.",
                        ),
                        "designation": openapi.Schema(
                            type=openapi.TYPE_STRING,
                            description="Current job title/position (max 100 characters)",
                            example="Senior Software Engineer",
                        ),
                        "company": openapi.Schema(
                            type=openapi.TYPE_STRING,
                            description="Current company or organization name (max 150 characters). Optional.",
                            example="Tech Corp Inc.",
                        ),
                        "experience_years": openapi.Schema(
                            type=openapi.TYPE_INTEGER,
                            description="Total years of professional experience (0-50)",
                            example=5,
                        ),
                        "available_time_slots": openapi.Schema(
                            type=openapi.TYPE_ARRAY,
                            description="Weekly availability schedule. Array of time slots with day, start_time, and end_time. Required 1-20 slots.",
                            items=openapi.Schema(
                                type=openapi.TYPE_OBJECT,
                                properties={
                                    "day": openapi.Schema(
                                        type=openapi.TYPE_STRING,
                                        enum=[
                                            "monday",
                                            "tuesday",
                                            "wednesday",
                                            "thursday",
                                            "friday",
                                            "saturday",
                                            "sunday",
                                        ],
                                        description="Day of the week (lowercase)",
                                    ),
                                    "start_time": openapi.Schema(
                                        type=openapi.TYPE_STRING,
                                        description="Start time in HH:MM format (24-hour)",
                                        example="09:00",
                                    ),
                                    "end_time": openapi.Schema(
                                        type=openapi.TYPE_STRING,
                                        description="End time in HH:MM format (24-hour). Must be after start_time.",
                                        example="17:00",
                                    ),
                                },
                            ),
                            example=[
                                {
                                    "day": "monday",
                                    "start_time": "09:00",
                                    "end_time": "17:00",
                                },
                                {
                                    "day": "wednesday",
                                    "start_time": "14:00",
                                    "end_time": "18:00",
                                },
                            ],
                        ),
                    },
                ),
                "interviewer": openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    description='Interviewer-specific fields. ONLY available for users with "taker" role.',
                    properties={
                        "expertise_areas": openapi.Schema(
                            type=openapi.TYPE_ARRAY,
                            description='List of expertise areas with proficiency levels. Each area must have "area" (name) and "level" (beginner/intermediate/expert). Required 1-20 areas.',
                            items=openapi.Schema(
                                type=openapi.TYPE_OBJECT,
                                properties={
                                    "area": openapi.Schema(
                                        type=openapi.TYPE_STRING,
                                        description='Expertise area name (e.g., "System Design", "Python")',
                                        example="System Design",
                                    ),
                                    "level": openapi.Schema(
                                        type=openapi.TYPE_STRING,
                                        enum=["beginner", "intermediate", "expert"],
                                        description="Proficiency level in this area",
                                    ),
                                },
                            ),
                            example=[
                                {"area": "System Design", "level": "expert"},
                                {"area": "Python", "level": "intermediate"},
                            ],
                        ),
                        "interviewing_experience_years": openapi.Schema(
                            type=openapi.TYPE_INTEGER,
                            description="Total years of experience conducting interviews (0-50)",
                            example=3,
                        ),
                        "credits_per_interview": openapi.Schema(
                            type=openapi.TYPE_INTEGER,
                            description="Credits/fees charged per interview session. Minimum 1, maximum 10000.",
                            example=150,
                        ),
                        "linkedin_profile_url": openapi.Schema(
                            type=openapi.TYPE_STRING,
                            description="LinkedIn profile URL for verification purposes (e.g., https://linkedin.com/in/username). Optional.",
                            example="https://linkedin.com/in/johndoe",
                        ),
                    },
                ),
                "interviewee": openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    description='Interviewee-specific fields. ONLY available for users with "attender" role.',
                    properties={
                        "skills": openapi.Schema(
                            type=openapi.TYPE_ARRAY,
                            description='List of skills with proficiency levels. Each skill must have "skill" (name) and "level" (beginner/intermediate/expert). Required 1-20 skills.',
                            items=openapi.Schema(
                                type=openapi.TYPE_OBJECT,
                                properties={
                                    "skill": openapi.Schema(
                                        type=openapi.TYPE_STRING,
                                        description='Skill name (e.g., "Python", "JavaScript", "React")',
                                        example="Python",
                                    ),
                                    "level": openapi.Schema(
                                        type=openapi.TYPE_STRING,
                                        enum=["beginner", "intermediate", "expert"],
                                        description="Proficiency level in this skill",
                                    ),
                                },
                            ),
                            example=[
                                {"skill": "Python", "level": "expert"},
                                {"skill": "React", "level": "intermediate"},
                            ],
                        ),
                        "target_role": openapi.Schema(
                            type=openapi.TYPE_STRING,
                            description="The job role/position you are targeting (max 100 characters)",
                            example="Senior Software Engineer",
                        ),
                        "preferred_interview_language": openapi.Schema(
                            type=openapi.TYPE_STRING,
                            description="Preferred language for conducting interviews (max 50 characters)",
                            example="English",
                        ),
                        "career_goal": openapi.Schema(
                            type=openapi.TYPE_STRING,
                            enum=["finding_jobs", "switching_jobs"],
                            description='Your current career objective. Use "finding_jobs" if you are looking for new opportunities, "switching_jobs" if you want to change your current job.',
                        ),
                    },
                ),
            },
        ),
        responses={
            200: openapi.Response(
                description="Profile updated successfully",
                schema=UserProfileSerializer,
                examples={
                    "application/json": {
                        "roles": ["taker", "attender"],
                        "role": "taker",
                        "name": "John Doe",
                        "phone_prefix": "+91",
                        "mobile_number": "9876543210",
                        "bio": "Senior software engineer with 5+ years of experience...",
                        "designation": "Senior Software Engineer",
                        "company": "Tech Corp Inc.",
                        "experience_years": 5,
                        "available_time_slots": [
                            {
                                "day": "monday",
                                "start_time": "09:00",
                                "end_time": "17:00",
                            }
                        ],
                        "current_position": "Senior Software Engineer",
                        "linkedin_profile_url": "https://linkedin.com/in/johndoe",
                        "onboarding_completed": True,
                        "onboarding_progress": 100,
                        "interviewer_profile": {
                            "expertise_areas": [
                                {"area": "System Design", "level": "expert"}
                            ],
                            "interviewing_experience_years": 3,
                            "credits_per_interview": 150,
                            "linkedin_profile_url": "https://linkedin.com/in/johndoe",
                        },
                        "interviewee_profile": {
                            "skills": [{"skill": "Python", "level": "expert"}],
                            "target_role": "Tech Lead",
                            "preferred_interview_language": "English",
                            "career_goal": "switching_jobs",
                        },
                    }
                },
            ),
            400: openapi.Response(
                description="Validation Error - Invalid field values",
                examples={
                    "application/json": {
                        "common": {
                            "mobile_number": [
                                "Invalid mobile number format. Enter digits only (6-15 digits)."
                            ],
                            "bio": ["Ensure this field has at least 10 characters."],
                        }
                    }
                },
            ),
            401: openapi.Response(
                description="Unauthorized - Authentication credentials were not provided or are invalid",
                examples={
                    "application/json": {
                        "detail": "Authentication credentials were not provided."
                    }
                },
            ),
            403: openapi.Response(
                description="Role Permission Error - Trying to update fields for a role you don't have",
                examples={
                    "application/json": {
                        "interviewer": "You do not have the 'interviewer' (taker) role, so you cannot update these fields."
                    }
                },
            ),
        },
    )
    
    def put(self, request):
        """
        Update current user's profile.

        Supports partial updates via nested structure. You only need to include
        the sections and fields you want to update.

        Sections:
        - common: Basic profile fields (all users)
        - interviewer: Interviewer-specific fields (taker role only)
        - interviewee: Interviewee-specific fields (attender role only)
        """
        serializer = ProfileUpdateSerializer(
            instance=request.user.profile,
            data=request.data,
            context={"request": request},
            partial=True,
        )

        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        serializer.save()

        # Return full updated profile data
        return Response(
            UserProfileSerializer(request.user.profile).data, status=status.HTTP_200_OK
        )


@swagger_auto_schema(
    method="get",
    tags=["Role Management"],
    operation_description="Get available roles and current user roles",
    responses={
        200: openapi.Response(
            description="Available roles and current user roles",
            examples={
                "application/json": {
                    "message": "Select or change your roles",
                    "current_roles": ["attender"],
                    "has_roles": True,
                    "available_roles": [
                        {
                            "name": "attender",
                            "display_name": "Interview Attender",
                            "description": "Can attend interviews and send interview requests.",
                        },
                        {
                            "name": "taker",
                            "display_name": "Interview Taker",
                            "description": "Can conduct interviews and receive interview requests.",
                        },
                    ],
                    "user_info": {
                        "email": "user@example.com",
                        "username": "johndoe",
                        "authenticated": True,
                    },
                }
            },
        )
    },
)
@swagger_auto_schema(
    method="post",
    tags=["Role Management"],
    operation_description="Set or change user roles (supports multiple roles)",
    request_body=openapi.Schema(
        type=openapi.TYPE_OBJECT,
        required=["roles"],
        properties={
            "roles": openapi.Schema(
                type=openapi.TYPE_ARRAY,
                items=openapi.Schema(
                    type=openapi.TYPE_STRING, enum=["attender", "taker"]
                ),
                description='List of roles to assign. Can be ["attender"], ["taker"], or ["attender", "taker"] for both.',
                example=["attender", "taker"],
            )
        },
    ),
    responses={
        200: openapi.Response(
            description="Roles set successfully",
            examples={
                "application/json": {
                    "success": True,
                    "message": "Roles updated successfully",
                    "roles": ["attender", "taker"],
                    "user_info": {
                        "email": "user@example.com",
                        "username": "johndoe",
                        "roles": ["attender", "taker"],
                    },
                    "next_steps": {
                        "dashboard": "/dashboard/",
                        "profile": "/api/profile/",
                        "message": "You can now access the dashboard and other protected endpoints",
                    },
                }
            },
        ),
        400: openapi.Response(
            description="Invalid roles",
            examples={
                "application/json": {
                    "error": "Invalid roles. Each role must be one of: attender, taker"
                }
            },
        ),
    },
)
@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def select_role_view(request):
    """
    API endpoint for role selection with multi-role support.

    GET: Returns available roles and current user roles.
    POST: Sets or changes user roles. Accepts a list of roles.

    Examples:
        - Single role: {"roles": ["attender"]}
        - Single role: {"roles": ["taker"]}
        - Both roles:  {"roles": ["attender", "taker"]}
    """
    user = request.user

    try:
        profile = user.profile
    except UserProfile.DoesNotExist:
        profile = UserProfile.objects.create(user=user)
        logger.info(f"Created missing profile for user {user.email}")

    if request.method == "GET":
        current_roles = profile.get_role_names()
        return Response(
            {
                "message": "Select or change your roles using the POST endpoint below",
                "current_roles": current_roles,
                "has_roles": profile.has_any_role(),
                # Backward compatibility
                "current_role": profile.get_effective_role(),
                "user_info": {
                    "email": user.email,
                    "username": user.username,
                    "authenticated": True,
                    "has_role": profile.has_any_role(),  # Updated to check any role
                },
                "roles_description": {
                    "attender": "Interview Attender - Can attend interviews and send interview requests",
                    "taker": "Interview Taker - Can conduct interviews and receive interview requests",
                },
                "available_roles": AVAILABLE_ROLES,
                "instructions": (
                    "Use POST to select your role(s). "
                    "Send {'roles': ['attender']} for Interview Attender, "
                    "{'roles': ['taker']} for Interview Taker, "
                    "or {'roles': ['attender', 'taker']} for both roles."
                ),
            }
        )

    # ========== POST: Set or change roles ==========

    # Support both new format (roles array) and legacy format (single role)
    roles_data = request.data.get("roles")
    legacy_role = request.data.get("role")

    # Handle legacy single role format for backward compatibility
    if roles_data is None and legacy_role:
        roles_data = [legacy_role]
        logger.info(
            f"User {user.email} using legacy single-role format, converting to list"
        )

    if not roles_data:
        return Response(
            {
                "error": "Roles are required. Send {'roles': ['attender']} or {'roles': ['attender', 'taker']}"
            },
            status=400,
        )

    # Ensure roles_data is a list
    if isinstance(roles_data, str):
        roles_data = [roles_data]

    # Validate using serializer
    serializer = RoleSelectionSerializer(data={"roles": roles_data})
    if not serializer.is_valid():
        return Response(
            {
                "error": "Invalid roles",
                "details": serializer.errors,
                "valid_roles": ["attender", "taker"],
                "hint": "Send {'roles': ['attender']}, {'roles': ['taker']}, or {'roles': ['attender', 'taker']}",
            },
            status=400,
        )

    validated_roles = serializer.validated_data["roles"]
    old_roles = profile.get_role_names()

    # Set the new roles (uses set_roles which clears existing and adds new)
    profile.set_roles(validated_roles)

    new_roles = profile.get_role_names()
    logger.info(f"User {user.email} changed roles from {old_roles} to {new_roles}")
    
    # Award initial credits if attender role was added
    logger.info(f"DEBUG: Checking credit award - new_roles={new_roles}, old_roles={old_roles}")
    logger.info(f"DEBUG: 'attender' in new_roles = {'attender' in new_roles}")
    logger.info(f"DEBUG: 'attender' not in old_roles = {'attender' not in old_roles}")
    
    if "attender" in new_roles and "attender" not in old_roles:
        logger.info(f"DEBUG: Condition passed, calling handle_attender_role_assignment")
        try:
            from apps.credits.services import CreditService
            CreditService.award_initial_credits(user)
            logger.info(f"Triggered initial credits award for new attender {user.email}")
        except Exception as e:
            logger.error(f"Error awarding initial credits: {str(e)}")
    else:
        logger.info(f"DEBUG: Condition not met, NOT awarding credits")

    return Response(
        {
            "success": True,
            "message": f"Roles updated successfully: {', '.join(new_roles)}",
            "roles": new_roles,
            # Backward compatibility
            "role": profile.get_effective_role(),
            "user_info": {
                "email": user.email,
                "username": user.username,
                "roles": new_roles,
                "role": profile.get_effective_role(),  # Deprecated
            },
            "next_steps": {
                "dashboard": "/dashboard/",
                "profile": "/api/profile/",
                "onboarding": "/api/onboarding/status/",
                "message": "Complete your onboarding to access full platform features",
            },
        }
    )


@swagger_auto_schema(
    method="post",
    tags=["Role Management"],
    operation_summary="Add Role",
    operation_description="""
Add a new role without removing existing roles. This allows role switching without data loss.

**Use Cases:**
- User with 'attender' role wants to also become a 'taker'
- User with 'taker' role wants to also become an 'attender'

**Behavior:**
- Adds the new role to the user's existing roles
- Auto-creates the role-specific profile (InterviewerProfile or IntervieweeProfile) if missing
- Does NOT remove any existing roles or profile data
- Does NOT require re-onboarding for the original role

**Note:** Use `/api/select-role/` if you want to REPLACE all roles.
""",
    request_body=openapi.Schema(
        type=openapi.TYPE_OBJECT,
        required=["role"],
        properties={
            "role": openapi.Schema(
                type=openapi.TYPE_STRING,
                enum=["attender", "taker"],
                description='Role to add. Must be "attender" or "taker".',
                example="taker",
            )
        },
    ),
    responses={
        200: openapi.Response(
            description="Role added successfully",
            examples={
                "application/json": {
                    "success": True,
                    "message": "Role 'taker' added successfully",
                    "roles": ["attender", "taker"],
                    "new_role_added": "taker",
                    "profile_created": True,
                    "requires_onboarding": True,
                    "next_steps": {
                        "onboarding_status": "/api/onboarding/status/",
                        "message": "Complete the interviewer onboarding for your new role",
                    },
                }
            },
        ),
        400: openapi.Response(
            description="Invalid request",
            examples={
                "application/json": {
                    "error": "You already have this role",
                    "current_roles": ["attender", "taker"],
                }
            },
        ),
    },
)
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def add_role_view(request):
    """
    Add a new role without removing existing roles.
    
    This endpoint allows users to switch roles (e.g., attender to both roles)
    without losing their existing role data and onboarding progress.
    
    Auto-creates the role-specific profile if it doesn't exist.
    """
    user = request.user
    
    try:
        profile = user.profile
    except UserProfile.DoesNotExist:
        profile = UserProfile.objects.create(user=user)
        logger.info(f"Created missing profile for user {user.email}")
    
    role = request.data.get("role")
    
    if not role:
        return Response(
            {
                "error": "Role is required",
                "valid_roles": ["attender", "taker"],
            },
            status=400,
        )
    
    if role not in ["attender", "taker"]:
        return Response(
            {
                "error": f"Invalid role: '{role}'",
                "valid_roles": ["attender", "taker"],
            },
            status=400,
        )
    
    # Check if user already has this role
    current_roles = profile.get_role_names()
    if role in current_roles:
        return Response(
            {
                "error": f"You already have the '{role}' role",
                "current_roles": current_roles,
            },
            status=400,
        )
    
    # Add the new role (uses add_roles which doesn't remove existing)
    profile.add_roles([role])
    
    # Auto-create role-specific profile if missing
    profile_created = False
    if role == "taker":
        # Create InterviewerProfile if it doesn't exist
        try:
            profile.interviewer_profile
        except InterviewerProfile.DoesNotExist:
            InterviewerProfile.objects.create(user_profile=profile)
            profile_created = True
            logger.info(f"Auto-created InterviewerProfile for user {user.email}")
    elif role == "attender":
        # Create IntervieweeProfile if it doesn't exist
        try:
            profile.interviewee_profile
        except IntervieweeProfile.DoesNotExist:
            IntervieweeProfile.objects.create(user_profile=profile)
            profile_created = True
            logger.info(f"Auto-created IntervieweeProfile for user {user.email}")
        
        # Award initial credits for new attender
        try:
            from apps.credits.services import CreditService
            CreditService.award_initial_credits(user)
            logger.info(f"Triggered initial credits award for new attender {user.email}")
        except Exception as e:
            logger.error(f"Error awarding initial credits: {str(e)}")
    
    new_roles = profile.get_role_names()
    logger.info(f"User {user.email} added role '{role}'. Roles now: {new_roles}")
    
    # Check if new role needs onboarding
    requires_onboarding = False
    if role == "taker":
        requires_onboarding = not profile.is_interviewer_onboarding_complete()
    elif role == "attender":
        requires_onboarding = not profile.is_interviewee_onboarding_complete()
    
    return Response(
        {
            "success": True,
            "message": f"Role '{role}' added successfully",
            "roles": new_roles,
            "new_role_added": role,
            "profile_created": profile_created,
            "requires_onboarding": requires_onboarding,
            "is_both_roles": profile.is_both(),
            "next_steps": {
                "onboarding_status": "/api/onboarding/status/",
                "profile_update": "/api/profile/update/",
                "message": f"Complete the {'interviewer' if role == 'taker' else 'interviewee'} onboarding for your new role" if requires_onboarding else "Your new role is ready to use",
            },
        }
    )


# ========== ONBOARDING APIs ==========


@swagger_auto_schema(
    method="get",
    tags=["Onboarding"],
    operation_description="Get current user's onboarding status",
    responses={
        200: openapi.Response(
            description="Onboarding status",
            examples={
                "application/json": {
                    "success": True,
                    "onboarding_status": {
                        "onboarding_completed": False,
                        "required_steps": ["common", "interviewer"],
                        "completed_steps": {"common": True, "interviewer": False},
                        "pending_steps": ["interviewer"],
                        "progress_percentage": 50,
                    },
                    "user_roles": ["taker"],
                    "step_requirements": {
                        "common": {
                            "fields": [
                                "name",
                                "mobile_number",
                                "bio",
                                "designation",
                                "experience_years",
                                "available_time_slots",
                            ]
                        },
                        "interviewer": {
                            "fields": [
                                "expertise_areas",
                                "interviewing_experience_years",
                                "credits_per_interview",
                                "linkedin_profile_url",
                            ]
                        },
                    },
                }
            },
        ),
        403: "Role selection required",
    },
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def onboarding_status_view(request):
    """
    Get current user's onboarding status.

    Returns:
        - Overall completion status
        - Required steps based on roles
        - Completed and pending steps
        - Progress percentage
        - Field requirements for each step
    """
    user = request.user

    try:
        profile = user.profile
    except UserProfile.DoesNotExist:
        profile = UserProfile.objects.create(user=user)

    # Check if role is selected
    if not profile.has_any_role():
        return Response(
            {
                "success": False,
                "error": "Role selection required before onboarding",
                "redirect_url": "/api/select-role/",
            },
            status=403,
        )

    # Get onboarding status
    onboarding_status = profile.get_onboarding_status()
    user_roles = profile.get_role_names()

    # Build step requirements based on roles
    step_requirements = {
        "common": {
            "fields": [
                "name",
                "mobile_number",
                "bio",
                "designation",
                "company",
                "experience_years",
                "available_time_slots",
            ],
            "description": "Basic profile information required for all users",
        }
    }

    if profile.is_taker():
        step_requirements["interviewer"] = {
            "fields": [
                "expertise_areas",
                "interviewing_experience_years",
                "credits_per_interview",
                "linkedin_profile_url",
            ],
            "description": "Information for conducting interviews as an interviewer",
        }

    if profile.is_attender():
        step_requirements["interviewee"] = {
            "fields": [
                "skills",
                "target_role",
                "preferred_interview_language",
                "career_goal",
            ],
            "description": "Information for attending interviews as a candidate",
        }

    # Include current values for resumable onboarding
    current_values = {
        "common": {
            "name": profile.name,
            "phone_prefix": profile.phone_prefix,  # NEW
            "mobile_number": profile.mobile_number,
            "bio": profile.bio,
            "designation": profile.designation,
            "company": profile.company,  # NEW - common onboarding
            "experience_years": profile.experience_years,
            "available_time_slots": profile.available_time_slots or [],
        }
    }

    if profile.is_taker():
        try:
            interviewer_profile = profile.interviewer_profile
            current_values["interviewer"] = {
                "expertise_areas": interviewer_profile.expertise_areas or [],
                "interviewing_experience_years": interviewer_profile.interviewing_experience_years,
                "credits_per_interview": interviewer_profile.credits_per_interview,
                "linkedin_profile_url": interviewer_profile.linkedin_profile_url or "",
            }
        except InterviewerProfile.DoesNotExist:
            current_values["interviewer"] = {
                "expertise_areas": [],
                "interviewing_experience_years": 0,
                "credits_per_interview": 0,
                "linkedin_profile_url": "",
            }

    if profile.is_attender():
        try:
            interviewee_profile = profile.interviewee_profile
            current_values["interviewee"] = {
                "skills": interviewee_profile.skills or [],
                "target_role": interviewee_profile.target_role,
                "preferred_interview_language": interviewee_profile.preferred_interview_language,
                "career_goal": interviewee_profile.career_goal,
            }
        except IntervieweeProfile.DoesNotExist:
            current_values["interviewee"] = {
                "skills": [],
                "target_role": "",
                "preferred_interview_language": "",
                "career_goal": "",
            }

    return Response(
        {
            "success": True,
            "onboarding_status": onboarding_status,
            "user_roles": user_roles,
            "step_requirements": step_requirements,
            "current_values": current_values,
            "instructions": "Use POST /api/onboarding/step/ to complete each step",
        }
    )


@swagger_auto_schema(
    method="post",
    tags=["Onboarding"],
    operation_description="""
Submit a single onboarding step.

**Steps:**
- `common` - Required for ALL users
- `interviewer` - Required for users with 'taker' role
- `interviewee` - Required for users with 'attender' role

**Users with BOTH roles must complete ALL 3 steps.**

---

**1. Common Step (All Users):**
```json
{
  "step": "common",
  "data": {
    "name": "John Doe",
    "phone_prefix": "+91",
    "mobile_number": "9876543210",
    "bio": "Senior software engineer with 5+ years experience",
    "designation": "Senior Developer",
    "company": "Tech Corp",
    "experience_years": 5,
    "available_time_slots": [
      {"day": "monday", "start_time": "09:00", "end_time": "17:00"},
      {"day": "wednesday", "start_time": "14:00", "end_time": "18:00"}
    ]
  }
}
```

**2. Interviewer Step (Takers / Both Roles):**
```json
{
  "step": "interviewer",
  "data": {
    "expertise_areas": [
      {"skill": "System Design", "level": "expert"},
      {"skill": "Python", "level": "intermediate"}
    ],
    "interviewing_experience_years": 3,
    "credits_per_interview": 150,
    "linkedin_profile_url": "https://linkedin.com/in/johndoe"
  }
}
```

**3. Interviewee Step (Attenders / Both Roles):**
```json
{
  "step": "interviewee",
  "data": {
    "skills": [
      {"skill": "Java", "level": "intermediate"},
      {"skill": "React", "level": "beginner"}
    ],
    "target_role": "Senior Software Engineer",
    "preferred_interview_language": "English",
    "career_goal": "Transition to a senior backend role at a FAANG company"
  }
}
```

---

**Required Steps by Role:**
| Role | Required Steps |
|------|----------------|
| Attender only | common, interviewee |
| Taker only | common, interviewer |
| BOTH roles | common, interviewer, interviewee |
""",
    request_body=openapi.Schema(
        type=openapi.TYPE_OBJECT,
        required=["step", "data"],
        properties={
            "step": openapi.Schema(
                type=openapi.TYPE_STRING,
                enum=["common", "interviewer", "interviewee"],
                description="Onboarding step to complete",
            ),
            "data": openapi.Schema(
                type=openapi.TYPE_OBJECT,
                description="Step-specific data (see examples above)",
            ),
        },
    ),
    responses={
        200: openapi.Response(
            description="Step completed successfully",
            examples={
                "application/json": {
                    "success": True,
                    "message": "Onboarding step 'common' completed successfully",
                    "step": "common",
                    "onboarding_status": {
                        "onboarding_completed": False,
                        "pending_steps": ["interviewer"],
                    },
                }
            },
        ),
        400: "Validation error",
        403: "Role/step mismatch",
    },
)
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def onboarding_step_view(request):
    """
    Submit a single onboarding step.

    Steps:
        - common: name, phone_prefix, mobile_number, bio, designation, company, experience_years, available_time_slots
        - interviewer: expertise_areas (with levels), interviewing_experience_years, credits_per_interview, linkedin_profile_url
        - interviewee: skills (with levels), target_role, preferred_interview_language, career_goal

    Each step is validated and saved independently, allowing partial completion.
    """
    user = request.user

    try:
        profile = user.profile
    except UserProfile.DoesNotExist:
        profile = UserProfile.objects.create(user=user)

    # Check if role is selected
    if not profile.has_any_role():
        return Response(
            {
                "success": False,
                "error": "Role selection required before onboarding",
                "redirect_url": "/api/select-role/",
            },
            status=403,
        )

    step = request.data.get("step")
    data = request.data.get("data", {})

    if not step:
        return Response(
            {
                "success": False,
                "error": "Step name is required",
                "valid_steps": profile.get_required_onboarding_steps(),
            },
            status=400,
        )

    # Validate step is required for user's roles
    required_steps = profile.get_required_onboarding_steps()
    if step not in required_steps:
        return Response(
            {
                "success": False,
                "error": f"Step '{step}' is not required for your role(s)",
                "user_roles": profile.get_role_names(),
                "required_steps": required_steps,
            },
            status=403,
        )

    # Validate step data
    if step == "common":
        serializer = CommonOnboardingSerializer(data=data)
    elif step == "interviewer":
        serializer = InterviewerOnboardingSerializer(data=data)
    elif step == "interviewee":
        serializer = IntervieweeOnboardingSerializer(data=data)
    else:
        return Response(
            {
                "success": False,
                "error": "Invalid step name",
                "valid_steps": required_steps,
            },
            status=400,
        )

    if not serializer.is_valid():
        return Response(
            {
                "success": False,
                "error": "Validation failed",
                "details": serializer.errors,
            },
            status=400,
        )

    validated_data = serializer.validated_data

    # Save step data to appropriate model
    if step == "common":
        profile.name = validated_data["name"]
        profile.phone_prefix = validated_data.get("phone_prefix", "")  # NEW
        profile.mobile_number = validated_data["mobile_number"]
        profile.bio = validated_data["bio"]
        profile.designation = validated_data["designation"]
        profile.company = validated_data["company"]  # NEW - common onboarding
        profile.experience_years = validated_data["experience_years"]
        profile.available_time_slots = validated_data["available_time_slots"]
        # Also update legacy field for backward compatibility
        profile.current_position = validated_data["designation"]
        profile.save(
            update_fields=[
                "name",
                "phone_prefix",
                "mobile_number",
                "bio",
                "designation",
                "company",
                "experience_years",
                "available_time_slots",
                "current_position",
            ]
        )

    elif step == "interviewer":
        # Create or update InterviewerProfile
        interviewer_profile, created = InterviewerProfile.objects.get_or_create(
            user_profile=profile
        )
        interviewer_profile.expertise_areas = validated_data["expertise_areas"]
        interviewer_profile.interviewing_experience_years = validated_data[
            "interviewing_experience_years"
        ]
        interviewer_profile.credits_per_interview = validated_data[
            "credits_per_interview"
        ]
        # linkedin_profile_url is optional
        interviewer_profile.linkedin_profile_url = validated_data.get(
            "linkedin_profile_url", ""
        )
        interviewer_profile.save()
        logger.info(
            f"{'Created' if created else 'Updated'} InterviewerProfile for {user.email}"
        )

    elif step == "interviewee":
        # Create or update IntervieweeProfile
        interviewee_profile, created = IntervieweeProfile.objects.get_or_create(
            user_profile=profile
        )
        interviewee_profile.skills = validated_data["skills"]
        interviewee_profile.target_role = validated_data["target_role"]
        interviewee_profile.preferred_interview_language = validated_data[
            "preferred_interview_language"
        ]
        interviewee_profile.career_goal = validated_data["career_goal"]
        interviewee_profile.save()
        logger.info(
            f"{'Created' if created else 'Updated'} IntervieweeProfile for {user.email}"
        )

    # Recalculate onboarding completion (data-driven)
    profile.calculate_onboarding_completion()

    # Get updated status
    onboarding_status = profile.get_onboarding_status()

    logger.info(f"User {user.email} completed onboarding step: {step}")

    response_data = {
        "success": True,
        "message": f"Onboarding step '{step}' completed successfully",
        "step": step,
        "onboarding_status": onboarding_status,
    }

    # If all steps complete, add congratulations message
    if onboarding_status["onboarding_completed"]:
        response_data["congratulations"] = (
            "Onboarding complete! You now have full access to the platform."
        )
        response_data["next_steps"] = {
            "dashboard": "/dashboard/",
            "profile": "/api/profile/",
        }
    else:
        response_data["next_step"] = {
            "pending_steps": onboarding_status["pending_steps"],
            "message": f"Complete remaining steps: {', '.join(onboarding_status['pending_steps'])}",
        }

    return Response(response_data)


@swagger_auto_schema(
    method="post",
    tags=["Onboarding"],
    operation_description="Complete all onboarding steps at once",
    request_body=openapi.Schema(
        type=openapi.TYPE_OBJECT,
        properties={
            "common": openapi.Schema(
                type=openapi.TYPE_OBJECT,
                description="Common onboarding data (required for all)",
                example={
                    "name": "John Doe",
                    "phone_prefix": "+91",
                    "mobile_number": "9876543210",
                    "bio": "Experienced software engineer...",
                    "designation": "Senior Developer",
                    "company": "Tech Corp Inc.",
                    "experience_years": 5,
                    "available_time_slots": [
                        {"day": "monday", "start_time": "09:00", "end_time": "17:00"}
                    ],
                },
            ),
            "interviewer": openapi.Schema(
                type=openapi.TYPE_OBJECT,
                description="Interviewer-specific data (if applicable)",
                example={
                    "expertise_areas": [
                        {"area": "Python", "level": "expert"},
                        {"area": "System Design", "level": "intermediate"},
                    ],
                    "interviewing_experience_years": 3,
                    "credits_per_interview": 100,
                    "linkedin_profile_url": "https://linkedin.com/in/johndoe",
                },
            ),
            "interviewee": openapi.Schema(
                type=openapi.TYPE_OBJECT,
                description="Interviewee-specific data (if applicable)",
                example={
                    "skills": [
                        {"skill": "Python", "level": "expert"},
                        {"skill": "JavaScript", "level": "intermediate"},
                    ],
                    "target_role": "Senior Software Engineer",
                    "preferred_interview_language": "English",
                    "career_goal": "switching_jobs",
                },
            ),
        },
    ),
    responses={
        200: openapi.Response(
            description="Onboarding completed successfully",
            examples={
                "application/json": {
                    "success": True,
                    "message": "Onboarding completed successfully!",
                    "onboarding_status": {
                        "onboarding_completed": True,
                        "progress_percentage": 100,
                    },
                }
            },
        ),
        400: "Validation error",
        403: "Role selection required",
    },
)
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def onboarding_complete_view(request):
    """
    Complete all onboarding steps at once.

    This endpoint allows submitting all required onboarding data in a single request.
    The request body should contain keys for each required step based on user's roles.

    Required based on roles:
    - common: Always required
    - interviewer: Required if user has 'taker' role
    - interviewee: Required if user has 'attender' role
    """
    user = request.user

    try:
        profile = user.profile
    except UserProfile.DoesNotExist:
        profile = UserProfile.objects.create(user=user)

    # Check if role is selected
    if not profile.has_any_role():
        return Response(
            {
                "success": False,
                "error": "Role selection required before onboarding",
                "redirect_url": "/api/select-role/",
            },
            status=403,
        )

    required_steps = profile.get_required_onboarding_steps()
    errors = {}
    validated_data = {}

    # Validate all required steps
    for step in required_steps:
        step_data = request.data.get(step, {})

        if not step_data:
            errors[step] = "This step is required"
            continue

        if step == "common":
            serializer = CommonOnboardingSerializer(data=step_data)
        elif step == "interviewer":
            serializer = InterviewerOnboardingSerializer(data=step_data)
        elif step == "interviewee":
            serializer = IntervieweeOnboardingSerializer(data=step_data)
        else:
            continue

        if serializer.is_valid():
            validated_data[step] = serializer.validated_data
        else:
            errors[step] = serializer.errors

    if errors:
        return Response(
            {
                "success": False,
                "error": "Validation failed for one or more steps",
                "details": errors,
                "required_steps": required_steps,
            },
            status=400,
        )

    # Save all validated data
    if "common" in validated_data:
        profile.name = validated_data["common"]["name"]
        profile.phone_prefix = validated_data["common"].get("phone_prefix", "")  # NEW
        profile.mobile_number = validated_data["common"]["mobile_number"]
        profile.bio = validated_data["common"]["bio"]
        profile.designation = validated_data["common"]["designation"]
        profile.company = validated_data["common"]["company"]  # NEW - common onboarding
        profile.experience_years = validated_data["common"]["experience_years"]
        profile.available_time_slots = validated_data["common"]["available_time_slots"]
        profile.current_position = validated_data["common"]["designation"]  # Legacy

    if "interviewer" in validated_data:
        interviewer_profile, created = InterviewerProfile.objects.get_or_create(
            user_profile=profile
        )
        interviewer_profile.expertise_areas = validated_data["interviewer"][
            "expertise_areas"
        ]
        interviewer_profile.interviewing_experience_years = validated_data[
            "interviewer"
        ]["interviewing_experience_years"]
        interviewer_profile.credits_per_interview = validated_data["interviewer"][
            "credits_per_interview"
        ]
        interviewer_profile.linkedin_profile_url = validated_data["interviewer"].get(
            "linkedin_profile_url", ""
        )
        interviewer_profile.save()

    if "interviewee" in validated_data:
        interviewee_profile, created = IntervieweeProfile.objects.get_or_create(
            user_profile=profile
        )
        interviewee_profile.skills = validated_data["interviewee"]["skills"]
        interviewee_profile.target_role = validated_data["interviewee"]["target_role"]
        interviewee_profile.preferred_interview_language = validated_data[
            "interviewee"
        ]["preferred_interview_language"]
        interviewee_profile.career_goal = validated_data["interviewee"]["career_goal"]
        interviewee_profile.save()

    # Save profile
    profile.save()

    # Recalculate onboarding completion (data-driven)
    profile.calculate_onboarding_completion()

    # Get final status
    onboarding_status = profile.get_onboarding_status()

    logger.info(f"User {user.email} completed full onboarding")

    return Response(
        {
            "success": True,
            "message": "Onboarding completed successfully!",
            "onboarding_status": onboarding_status,
            "next_steps": {
                "dashboard": "/dashboard/",
                "profile": "/api/profile/",
                "message": "You now have full access to the platform",
            },
        }
    )


# ========== PROFILE LISTING APIs (READ-ONLY) ==========


class BaseProfileListAPI(ListAPIView):
    """
    Base class for profile listing with common functionality.

    Supports optional filters (query params):
    - company: Filter by company name (case-insensitive contains)
    - designation: Filter by designation (case-insensitive contains)
    - skill: Search both interviewee.skills AND interviewer.expertise_areas
    - onboarding_completed: true|false

    Supports optional sorting (query param: sort):
    - name_asc: A → Z
    - name_desc: Z → A
    - verified: verified users first
    - unverified: unverified users first
    - credits_low: credits per interview (low → high)
    - credits_high: credits per interview (high → low)

    Always excludes the requesting user from results.
    """

    permission_classes = [IsAuthenticated]
    serializer_class = ProfileListSerializer

    # Valid sort options
    # credits_low_high/credits_high_low are aliases for credits_low/credits_high
    SORT_OPTIONS = [
        "name_asc",
        "name_desc",
        "verified",
        "unverified",
        "credits_low",
        "credits_high",
        "credits_low_high",
        "credits_high_low",
    ]

    def get_queryset(self):
        """Override in subclasses to filter by role."""
        return UserProfile.objects.none()

    def filter_queryset(self, queryset):
        """
        Apply filters and sorting, exclude requesting user.

        All filtering & sorting logic is centralized here per architectural requirements.

        NEW Filters:
        - verified: true|false - Filter by user verification status
        - experience_min: int - Minimum years of experience
        - experience_max: int - Maximum years of experience
        """
        queryset = super().filter_queryset(queryset)

        # Always exclude the requesting user from results
        queryset = queryset.exclude(user=self.request.user)

        # ========== FILTERS ==========

        # Filter by onboarding_completed
        onboarding_completed = self.request.query_params.get("onboarding_completed")
        if onboarding_completed is not None:
            if onboarding_completed.lower() == "true":
                queryset = queryset.filter(onboarding_completed=True)
            elif onboarding_completed.lower() == "false":
                queryset = queryset.filter(onboarding_completed=False)

        # NEW: Filter by verified status
        verified = self.request.query_params.get("verified")
        if verified is not None:
            if verified.lower() == "true":
                queryset = queryset.filter(is_verified_user=True)
            elif verified.lower() == "false":
                queryset = queryset.filter(is_verified_user=False)

        # Filter by company (case-insensitive contains)
        company = self.request.query_params.get("company")
        if company:
            queryset = queryset.filter(company__icontains=company)

        # Filter by designation (case-insensitive contains)
        designation = self.request.query_params.get("designation")
        if designation:
            queryset = queryset.filter(designation__icontains=designation)

        # Filter by skill (search both interviewee.skills AND interviewer.expertise_areas)
        skill = self.request.query_params.get("skill")
        if skill:
            # Search in interviewee_profile.skills (JSONField with {"skill": "name", "level": "..."})
            # AND in interviewer_profile.expertise_areas (JSONField with {"area": "name", "level": "..."})
            skill_filter = Q(interviewee_profile__skills__icontains=skill) | Q(
                interviewer_profile__expertise_areas__icontains=skill
            )
            queryset = queryset.filter(skill_filter)

        # NEW: Filter by experience range
        experience_min = self.request.query_params.get("experience_min")
        if experience_min:
            try:
                min_val = int(experience_min)
                queryset = queryset.filter(experience_years__gte=min_val)
            except ValueError:
                pass

        experience_max = self.request.query_params.get("experience_max")
        if experience_max:
            try:
                max_val = int(experience_max)
                queryset = queryset.filter(experience_years__lte=max_val)
            except ValueError:
                pass

        # ========== SORTING ==========

        sort = self.request.query_params.get("sort")
        if sort and sort in self.SORT_OPTIONS:
            queryset = self._apply_sorting(queryset, sort)

        return queryset.select_related("user").prefetch_related(
            "roles", "interviewee_profile", "interviewer_profile"
        )

    def _apply_sorting(self, queryset, sort_option):
        """
        Apply sorting based on the sort option.

        IMPORTANT: This uses is_verified_user (LinkedIn expert verification)
        NOT email verification (django-allauth).

        - is_verified_user = LinkedIn expert verification for interviewers
        - EmailAddress.verified = Email confirmation for signup (SEPARATE)
        """
        if sort_option == "name_asc":
            return queryset.order_by("name", "-created_at")

        elif sort_option == "name_desc":
            return queryset.order_by("-name", "-created_at")

        elif sort_option == "verified":
            # Sort by is_verified_user (LinkedIn expert verification)
            # Verified experts come first
            return queryset.order_by("-is_verified_user", "-created_at")

        elif sort_option == "unverified":
            # Unverified users come first
            return queryset.order_by("is_verified_user", "-created_at")

        elif sort_option in ["credits_low", "credits_low_high"]:
            # Sort by credits_per_interview low to high
            # Users without interviewer_profile should be at the end
            return queryset.annotate(
                credits=Coalesce(
                    "interviewer_profile__credits_per_interview", Value(999999)
                )
            ).order_by("credits", "-created_at")

        elif sort_option in ["credits_high", "credits_high_low"]:
            # Sort by credits_per_interview high to low
            # Users without interviewer_profile should be at the end
            return queryset.annotate(
                credits=Coalesce("interviewer_profile__credits_per_interview", Value(0))
            ).order_by("-credits", "-created_at")

        return queryset

    def list(self, request, *args, **kwargs):
        """
        Override list to add metadata to response.

        When sort=verified:
        - Returns ONLY verified expert users (is_verified_user=True)
        - Excludes unverified users from results

        Response includes:
        - matching_verified_count: Count of verified users matching filters
        - total_count: Total users before verification filter
        - matching_count: Users with match_score > 0
        """
        queryset = self.filter_queryset(self.get_queryset())

        # Calculate total count BEFORE verification filter
        total_count = queryset.count()

        # Calculate verified count
        matching_verified_count = queryset.filter(is_verified_user=True).count()

        # Calculate matching_count (users with match_score > 0)
        try:
            matching_count = queryset.filter(match_score__gt=0).count()
        except Exception:
            matching_count = 0

        # If sort=verified, filter to ONLY show verified users
        sort = self.request.query_params.get("sort")
        if sort == "verified":
            queryset = queryset.filter(is_verified_user=True)

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            response = self.get_paginated_response(serializer.data)
            response.data["matching_count"] = matching_count
            response.data["matching_verified_count"] = matching_verified_count
            response.data["total_count"] = total_count
            return response

        serializer = self.get_serializer(queryset, many=True)
        return Response(
            {
                "matching_count": matching_count,
                "matching_verified_count": matching_verified_count,
                "total_count": total_count,
                "results": serializer.data,
            }
        )


class AttendersListAPI(BaseProfileListAPI):
    """
    List all users with 'attender' (Interviewee) role.

    GET /api/profiles/attenders/
    GET /api/profiles/attenders/?onboarding_completed=true
    """

    @swagger_auto_schema(
        tags=["Profile"],
        operation_description="""
        List all users with Interview Attender (Interviewee) role.
        
        Supports optional filters and sorting.
        """,
        manual_parameters=[
            openapi.Parameter(
                "onboarding_completed",
                openapi.IN_QUERY,
                description="Filter by onboarding completion status",
                type=openapi.TYPE_BOOLEAN,
                required=False,
            ),
            openapi.Parameter(
                "company",
                openapi.IN_QUERY,
                description="Filter by company name (case-insensitive contains)",
                type=openapi.TYPE_STRING,
                required=False,
            ),
            openapi.Parameter(
                "designation",
                openapi.IN_QUERY,
                description="Filter by designation (case-insensitive contains)",
                type=openapi.TYPE_STRING,
                required=False,
            ),
            openapi.Parameter(
                "skill",
                openapi.IN_QUERY,
                description="Search skills (searches both interviewee.skills and interviewer.expertise_areas)",
                type=openapi.TYPE_STRING,
                required=False,
            ),
            openapi.Parameter(
                "sort",
                openapi.IN_QUERY,
                description="Sort option: name_asc, name_desc, verified, unverified, credits_low, credits_high",
                type=openapi.TYPE_STRING,
                enum=[
                    "name_asc",
                    "name_desc",
                    "verified",
                    "unverified",
                    "credits_low",
                    "credits_high",
                ],
                required=False,
            ),
        ],
        responses={200: ProfileListSerializer(many=True)},
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        """Get all profiles with attender role, ranked by match with requesting taker."""
        requesting_user = self.request.user
        queryset = UserProfile.objects.filter(
            roles__name=Role.ATTENDER, roles__is_active=True
        ).distinct()

        # Get requesting user's profile
        try:
            requesting_profile = requesting_user.profile
        except UserProfile.DoesNotExist:
            # No requesting profile - return unranked
            return queryset.annotate(
                match_score=Value(0, output_field=IntegerField())
            ).order_by("-created_at")

        # Only rank if requesting user is a taker
        if not requesting_profile.is_taker():
            return queryset.annotate(
                match_score=Value(0, output_field=IntegerField())
            ).order_by("-created_at")

        # Get requesting user's data for matching
        try:
            requesting_interviewer = requesting_profile.interviewer_profile
            requesting_expertise = requesting_interviewer.expertise_areas or []
        except InterviewerProfile.DoesNotExist:
            requesting_expertise = []

        requesting_time_slots = requesting_profile.available_time_slots or []

        # Extract skill/area names for comparison
        requesting_expertise_names = {
            item.get("area", "").lower()
            for item in requesting_expertise
            if item.get("area")
        }
        requesting_days = {
            slot.get("day", "").lower()
            for slot in requesting_time_slots
            if slot.get("day")
        }

        # Annotate with match_score using database-level logic
        queryset = queryset.annotate(
            match_score=Case(
                # Check if IntervieweeProfile exists and has matching skills + time slots
                When(
                    Q(interviewee_profile__isnull=False)
                    & Q(interviewee_profile__skills__isnull=False)
                    & self._build_skill_match_q(requesting_expertise_names)
                    & self._build_time_match_q(requesting_days),
                    then=Value(30, output_field=IntegerField()),
                ),
                # Skill match only
                When(
                    Q(interviewee_profile__isnull=False)
                    & Q(interviewee_profile__skills__isnull=False)
                    & self._build_skill_match_q(requesting_expertise_names),
                    then=Value(20, output_field=IntegerField()),
                ),
                # Time slot match only
                When(
                    self._build_time_match_q(requesting_days),
                    then=Value(10, output_field=IntegerField()),
                ),
                # No match
                default=Value(0, output_field=IntegerField()),
                output_field=IntegerField(),
            )
        )

        return queryset.order_by("-match_score", "-created_at")

    def _build_skill_match_q(self, requesting_expertise_names):
        """Build Q object for skill matching using JSONField overlap check."""
        if not requesting_expertise_names:
            return Q(pk__in=[])

        # Check if any skill in interviewee's skills matches requesting expertise
        # Using JSON contains check for PostgreSQL
        skill_conditions = Q(pk__in=[])
        for skill_name in requesting_expertise_names:
            # Match if skills array contains an object with matching skill name (case-insensitive)
            skill_conditions |= Q(interviewee_profile__skills__icontains=skill_name)

        return skill_conditions

    def _build_time_match_q(self, requesting_days):
        """Build Q object for time slot matching."""
        if not requesting_days:
            return Q(pk__in=[])

        # Check if any day in available_time_slots matches
        day_conditions = Q(pk__in=[])
        for day in requesting_days:
            day_conditions |= Q(available_time_slots__icontains=day)

        return day_conditions


class TakersListAPI(BaseProfileListAPI):
    """
    List all users with 'taker' (Interviewer) role.

    GET /api/profiles/takers/
    GET /api/profiles/takers/?onboarding_completed=true
    """

    @swagger_auto_schema(
        tags=["Profile"],
        operation_description="""
        List all users with Interview Taker (Interviewer) role.
        
        Supports optional filters and sorting.
        """,
        manual_parameters=[
            openapi.Parameter(
                "onboarding_completed",
                openapi.IN_QUERY,
                description="Filter by onboarding completion status",
                type=openapi.TYPE_BOOLEAN,
                required=False,
            ),
            openapi.Parameter(
                "company",
                openapi.IN_QUERY,
                description="Filter by company name (case-insensitive contains)",
                type=openapi.TYPE_STRING,
                required=False,
            ),
            openapi.Parameter(
                "designation",
                openapi.IN_QUERY,
                description="Filter by designation (case-insensitive contains)",
                type=openapi.TYPE_STRING,
                required=False,
            ),
            openapi.Parameter(
                "skill",
                openapi.IN_QUERY,
                description="Search skills (searches both interviewee.skills and interviewer.expertise_areas)",
                type=openapi.TYPE_STRING,
                required=False,
            ),
            openapi.Parameter(
                "sort",
                openapi.IN_QUERY,
                description="Sort option: name_asc, name_desc, verified, unverified, credits_low, credits_high",
                type=openapi.TYPE_STRING,
                enum=[
                    "name_asc",
                    "name_desc",
                    "verified",
                    "unverified",
                    "credits_low",
                    "credits_high",
                ],
                required=False,
            ),
        ],
        responses={200: ProfileListSerializer(many=True)},
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        """Get all profiles with taker role, ranked by match with requesting attender."""
        requesting_user = self.request.user
        queryset = UserProfile.objects.filter(
            roles__name=Role.TAKER, roles__is_active=True
        ).distinct()

        # Get requesting user's profile
        try:
            requesting_profile = requesting_user.profile
        except UserProfile.DoesNotExist:
            # No requesting profile - return unranked
            return queryset.annotate(
                match_score=Value(0, output_field=IntegerField())
            ).order_by("-created_at")

        # Only rank if requesting user is an attender
        if not requesting_profile.is_attender():
            return queryset.annotate(
                match_score=Value(0, output_field=IntegerField())
            ).order_by("-created_at")

        # Get requesting user's data for matching
        try:
            requesting_interviewee = requesting_profile.interviewee_profile
            requesting_skills = requesting_interviewee.skills or []
        except IntervieweeProfile.DoesNotExist:
            requesting_skills = []

        requesting_time_slots = requesting_profile.available_time_slots or []

        # Extract skill/area names for comparison
        requesting_skill_names = {
            item.get("skill", "").lower()
            for item in requesting_skills
            if item.get("skill")
        }
        requesting_days = {
            slot.get("day", "").lower()
            for slot in requesting_time_slots
            if slot.get("day")
        }

        # Annotate with match_score using database-level logic
        queryset = queryset.annotate(
            match_score=Case(
                # Check if InterviewerProfile exists and has matching expertise + time slots
                When(
                    Q(interviewer_profile__isnull=False)
                    & Q(interviewer_profile__expertise_areas__isnull=False)
                    & self._build_expertise_match_q(requesting_skill_names)
                    & self._build_time_match_q(requesting_days),
                    then=Value(30, output_field=IntegerField()),
                ),
                # Expertise match only
                When(
                    Q(interviewer_profile__isnull=False)
                    & Q(interviewer_profile__expertise_areas__isnull=False)
                    & self._build_expertise_match_q(requesting_skill_names),
                    then=Value(20, output_field=IntegerField()),
                ),
                # Time slot match only
                When(
                    self._build_time_match_q(requesting_days),
                    then=Value(10, output_field=IntegerField()),
                ),
                # No match
                default=Value(0, output_field=IntegerField()),
                output_field=IntegerField(),
            )
        )

        return queryset.order_by("-match_score", "-created_at")

    def _build_expertise_match_q(self, requesting_skill_names):
        """Build Q object for expertise matching using JSONField overlap check."""
        if not requesting_skill_names:
            return Q(pk__in=[])

        # Check if any expertise area matches requesting skills
        expertise_conditions = Q(pk__in=[])
        for skill_name in requesting_skill_names:
            # Match if expertise_areas array contains an object with matching area name (case-insensitive)
            expertise_conditions |= Q(
                interviewer_profile__expertise_areas__icontains=skill_name
            )

        return expertise_conditions

    def _build_time_match_q(self, requesting_days):
        """Build Q object for time slot matching."""
        if not requesting_days:
            return Q(pk__in=[])

        # Check if any day in available_time_slots matches
        day_conditions = Q(pk__in=[])
        for day in requesting_days:
            day_conditions |= Q(available_time_slots__icontains=day)

        return day_conditions


class BothRolesListAPI(BaseProfileListAPI):
    """
    List all users who have BOTH 'attender' AND 'taker' roles.

    GET /api/profiles/both/
    GET /api/profiles/both/?onboarding_completed=true
    """

    @swagger_auto_schema(
        tags=["Profile"],
        operation_description="""
        List all users with both Interview Attender AND Interview Taker roles.
        
        Supports optional filters and sorting.
        """,
        manual_parameters=[
            openapi.Parameter(
                "onboarding_completed",
                openapi.IN_QUERY,
                description="Filter by onboarding completion status",
                type=openapi.TYPE_BOOLEAN,
                required=False,
            ),
            openapi.Parameter(
                "company",
                openapi.IN_QUERY,
                description="Filter by company name (case-insensitive contains)",
                type=openapi.TYPE_STRING,
                required=False,
            ),
            openapi.Parameter(
                "designation",
                openapi.IN_QUERY,
                description="Filter by designation (case-insensitive contains)",
                type=openapi.TYPE_STRING,
                required=False,
            ),
            openapi.Parameter(
                "skill",
                openapi.IN_QUERY,
                description="Search skills (searches both interviewee.skills and interviewer.expertise_areas)",
                type=openapi.TYPE_STRING,
                required=False,
            ),
            openapi.Parameter(
                "sort",
                openapi.IN_QUERY,
                description="Sort option: name_asc, name_desc, verified, unverified, credits_low, credits_high",
                type=openapi.TYPE_STRING,
                enum=[
                    "name_asc",
                    "name_desc",
                    "verified",
                    "unverified",
                    "credits_low",
                    "credits_high",
                ],
                required=False,
            ),
        ],
        responses={200: ProfileListSerializer(many=True)},
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        """Get all profiles with BOTH roles, ranked by match in both dimensions."""
        requesting_user = self.request.user
        # Users who have both roles
        queryset = (
            UserProfile.objects.filter(roles__name=Role.ATTENDER, roles__is_active=True)
            .filter(roles__name=Role.TAKER, roles__is_active=True)
            .distinct()
        )

        # Get requesting user's profile
        try:
            requesting_profile = requesting_user.profile
        except UserProfile.DoesNotExist:
            # No requesting profile - return unranked
            return queryset.annotate(
                match_score=Value(0, output_field=IntegerField())
            ).order_by("-created_at")

        # Collect requesting user's data for both dimensions
        requesting_skills = []
        requesting_expertise = []

        try:
            requesting_interviewee = requesting_profile.interviewee_profile
            requesting_skills = requesting_interviewee.skills or []
        except IntervieweeProfile.DoesNotExist:
            pass

        try:
            requesting_interviewer = requesting_profile.interviewer_profile
            requesting_expertise = requesting_interviewer.expertise_areas or []
        except InterviewerProfile.DoesNotExist:
            pass

        requesting_time_slots = requesting_profile.available_time_slots or []

        # Extract names for comparison
        requesting_skill_names = {
            item.get("skill", "").lower()
            for item in requesting_skills
            if item.get("skill")
        }
        requesting_expertise_names = {
            item.get("area", "").lower()
            for item in requesting_expertise
            if item.get("area")
        }
        requesting_days = {
            slot.get("day", "").lower()
            for slot in requesting_time_slots
            if slot.get("day")
        }

        # Combine both skill sets for matching users with both roles
        all_requesting_names = requesting_skill_names | requesting_expertise_names

        # Annotate with match_score considering both dimensions
        queryset = queryset.annotate(
            match_score=Case(
                # Best match: both skill/expertise overlap AND time slot overlap
                When(
                    (
                        self._build_both_match_q(all_requesting_names)
                        & self._build_time_match_q(requesting_days)
                    ),
                    then=Value(30, output_field=IntegerField()),
                ),
                # Skill/expertise match only
                When(
                    self._build_both_match_q(all_requesting_names),
                    then=Value(20, output_field=IntegerField()),
                ),
                # Time slot match only
                When(
                    self._build_time_match_q(requesting_days),
                    then=Value(10, output_field=IntegerField()),
                ),
                # No match
                default=Value(0, output_field=IntegerField()),
                output_field=IntegerField(),
            )
        )

        return queryset.order_by("-match_score", "-created_at")

    def _build_both_match_q(self, all_requesting_names):
        """Build Q object for matching in either interviewee skills OR interviewer expertise."""
        if not all_requesting_names:
            return Q(pk__in=[])

        # Match if either their interviewer expertise or interviewee skills match our data
        match_conditions = Q(pk__in=[])
        for name in all_requesting_names:
            match_conditions |= Q(interviewer_profile__expertise_areas__icontains=name)
            match_conditions |= Q(interviewee_profile__skills__icontains=name)

        return match_conditions

    def _build_time_match_q(self, requesting_days):
        """Build Q object for time slot matching."""
        if not requesting_days:
            return Q(pk__in=[])

        # Check if any day in available_time_slots matches
        day_conditions = Q(pk__in=[])
        for day in requesting_days:
            day_conditions |= Q(available_time_slots__icontains=day)

        return day_conditions


# ========== USER DETAIL API (NEW) ==========


class UserDetailAPI(APIView):
    """
    API endpoint for getting user profile by UUID.

    GET /api/users/{uuid}/

    Access rules:
    - Normal users: Can only view public profile fields
    - Admin users: Can view full profile with all fields
    """

    permission_classes = [IsAuthenticated]

    def _get_profile_by_uuid(self, user_id):
        """
        Helper to get UserProfile by public_id (UUID).
        """
        try:
            return UserProfile.objects.select_related("user").get(public_id=user_id)
        except UserProfile.DoesNotExist:
            return None

    @swagger_auto_schema(
        tags=["Users"],
        operation_description="""
        Get user profile by UUID.
        
        - Normal users see limited public fields
        - Admin users see full profile including sensitive data
        """,
        responses={
            200: openapi.Response(
                description="User profile",
                examples={
                    "application/json": {
                        "user_id": "550e8400-e29b-41d4-a716-446655440000",
                        "name": "John Doe",
                        "bio": "Software Engineer",
                        "designation": "Senior Developer",
                        "roles": ["attender", "taker"],
                    }
                },
            ),
            404: "User not found",
        },
    )
    def get(self, request, user_id):
        """Get user profile by UUID."""
        profile = self._get_profile_by_uuid(user_id)
        if not profile:
            return Response(
                {"error": "User not found"}, status=status.HTTP_404_NOT_FOUND
            )

        # Check if requesting user is admin
        is_admin = request.user.is_staff or request.user.is_superuser

        if is_admin:
            serializer = UserFullProfileSerializer(profile)
        else:
            serializer = UserPublicProfileSerializer(profile)

        return Response(serializer.data)


# ========== ADMIN APIs (NEW) ==========


class AdminUserListAPI(ListAPIView):
    """
    Admin-only API for listing all users with full profile data.

    GET /api/admin/users/
    GET /api/admin/users/?role=attender
    GET /api/admin/users/?onboarding_completed=true
    GET /api/admin/users/?is_active=true
    """

    permission_classes = [IsAuthenticated, IsAdmin]
    serializer_class = UserFullProfileSerializer

    @swagger_auto_schema(
        tags=["Admin"],
        operation_description="List all users with full profile data (Admin only)",
        manual_parameters=[
            openapi.Parameter(
                "role",
                openapi.IN_QUERY,
                description="Filter by EXACT role: attender (only attender), taker (only taker), both (has both roles)",
                type=openapi.TYPE_STRING,
                required=False,
            ),
            openapi.Parameter(
                "onboarding_completed",
                openapi.IN_QUERY,
                description="Filter by onboarding completion status",
                type=openapi.TYPE_BOOLEAN,
                required=False,
            ),
            openapi.Parameter(
                "is_active",
                openapi.IN_QUERY,
                description="Filter by user active status",
                type=openapi.TYPE_BOOLEAN,
                required=False,
            ),
        ],
        responses={200: UserFullProfileSerializer(many=True)},
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    def list(self, request, *args, **kwargs):
        """Override list to add total_count to response."""
        queryset = self.filter_queryset(self.get_queryset())

        # Get total count before pagination
        total_count = queryset.count()

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            response = self.get_paginated_response(serializer.data)
            response.data["total_count"] = total_count
            return response

        serializer = self.get_serializer(queryset, many=True)
        return Response({"total_count": total_count, "results": serializer.data})

    def get_queryset(self):
        queryset = (
            UserProfile.objects.select_related("user").prefetch_related("roles").all()
        )

        # Filter by role with EXACT matching
        role = self.request.query_params.get("role")
        if role:
            # Annotate with role counts for exact matching
            queryset = queryset.annotate(
                attender_count=Count(
                    "roles", filter=Q(roles__name=Role.ATTENDER, roles__is_active=True)
                ),
                taker_count=Count(
                    "roles", filter=Q(roles__name=Role.TAKER, roles__is_active=True)
                ),
            )

            if role == Role.ATTENDER:
                # ONLY attender role (has attender, does NOT have taker)
                queryset = queryset.filter(attender_count__gte=1, taker_count=0)
            elif role == Role.TAKER:
                # ONLY taker role (has taker, does NOT have attender)
                queryset = queryset.filter(taker_count__gte=1, attender_count=0)
            elif role == "both":
                # BOTH roles (has both attender AND taker)
                queryset = queryset.filter(attender_count__gte=1, taker_count__gte=1)

        # Filter by onboarding status
        onboarding_completed = self.request.query_params.get("onboarding_completed")
        if onboarding_completed is not None:
            if onboarding_completed.lower() == "true":
                queryset = queryset.filter(onboarding_completed=True)
            elif onboarding_completed.lower() == "false":
                queryset = queryset.filter(onboarding_completed=False)

        # Filter by is_active
        is_active = self.request.query_params.get("is_active")
        if is_active is not None:
            if is_active.lower() == "true":
                queryset = queryset.filter(user__is_active=True)
            elif is_active.lower() == "false":
                queryset = queryset.filter(user__is_active=False)

        return queryset.distinct()


class AdminUserDetailAPI(APIView):
    """
    Admin-only API for viewing, updating, or deleting a user.

    Uses UUID (public_id) for external identification.

    GET /api/admin/users/{uuid}/
    PUT /api/admin/users/{uuid}/
    DELETE /api/admin/users/{uuid}/
    """

    permission_classes = [IsAuthenticated, IsAdmin]

    def _get_profile_by_uuid(self, user_id):
        """
        Helper to get UserProfile by public_id (UUID).

        UUID is public, integer ID is private.
        """
        try:
            return UserProfile.objects.select_related("user").get(public_id=user_id)
        except UserProfile.DoesNotExist:
            return None

    @swagger_auto_schema(
        tags=["Admin"],
        operation_description="Get full user profile by UUID (Admin only)",
        responses={200: UserFullProfileSerializer, 404: "User not found"},
    )
    def get(self, request, user_id):
        """Get full user profile by UUID."""
        profile = self._get_profile_by_uuid(user_id)
        if not profile:
            return Response(
                {"error": "User not found"}, status=status.HTTP_404_NOT_FOUND
            )

        serializer = UserFullProfileSerializer(profile)
        return Response(serializer.data)

    @swagger_auto_schema(
        tags=["Admin"],
        operation_description="Update user profile by UUID (Admin only)",
        request_body=AdminUserUpdateSerializer,
        responses={
            200: UserFullProfileSerializer,
            400: "Validation error",
            404: "User not found",
        },
    )
    def put(self, request, user_id):
        """Update user profile by UUID."""
        profile = self._get_profile_by_uuid(user_id)
        if not profile:
            return Response(
                {"error": "User not found"}, status=status.HTTP_404_NOT_FOUND
            )

        serializer = AdminUserUpdateSerializer(profile, data=request.data, partial=True)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        serializer.save()
        logger.info(
            f"Admin {request.user.email} updated profile for user {profile.user.email}"
        )

        return Response(UserFullProfileSerializer(profile).data)

    @swagger_auto_schema(
        tags=["Admin"],
        operation_description="Delete user by UUID (Admin only). This action is irreversible.",
        responses={
            200: openapi.Response(
                description="User deleted",
                examples={
                    "application/json": {
                        "success": True,
                        "message": "User deleted successfully",
                    }
                },
            ),
            400: "Cannot delete self or other admins",
            404: "User not found",
        },
    )
    def delete(self, request, user_id):
        """Delete a user by UUID."""
        profile = self._get_profile_by_uuid(user_id)
        if not profile:
            return Response(
                {"error": "User not found"}, status=status.HTTP_404_NOT_FOUND
            )

        user_to_delete = profile.user

        # Prevent self-deletion
        if user_to_delete == request.user:
            return Response(
                {"error": "You cannot delete yourself"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Prevent deleting other admins (except superuser can delete staff)
        if user_to_delete.is_superuser:
            return Response(
                {"error": "Cannot delete superuser accounts"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if user_to_delete.is_staff and not request.user.is_superuser:
            return Response(
                {"error": "Only superusers can delete staff accounts"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        email = user_to_delete.email
        user_to_delete.delete()  # This also deletes the profile via CASCADE

        logger.warning(f"Admin {request.user.email} deleted user {email}")

        return Response(
            {"success": True, "message": f"User {email} deleted successfully"}
        )


# ========== ADMIN VERIFICATION APIs ==========


class AdminVerifyUserAPI(APIView):
    """
    Manually verify a user (Admin only).

    POST /api/admin/users/{uuid}/verify/

    This marks the user as verified via admin verification.
    """

    permission_classes = [IsAuthenticated, IsAdmin]

    @swagger_auto_schema(
        tags=["Admin"],
        operation_description="Manually verify a user (Admin only)",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                "notes": openapi.Schema(
                    type=openapi.TYPE_STRING, description="Optional verification notes"
                )
            },
        ),
        responses={
            200: openapi.Response(
                description="User verified",
                examples={
                    "application/json": {
                        "success": True,
                        "message": "User verified successfully",
                        "verification_status": {
                            "is_verified": True,
                            "verified_via": "admin",
                            "verified_at": "2026-01-23T10:30:00Z",
                        },
                    }
                },
            ),
            400: "User already verified",
            404: "User not found",
        },
    )
    def post(self, request, user_id):
        """Manually verify a user."""
        try:
            profile = UserProfile.objects.get(public_id=user_id)
        except UserProfile.DoesNotExist:
            return Response(
                {"error": "User not found"}, status=status.HTTP_404_NOT_FOUND
            )

        if profile.is_verified_user:
            return Response(
                {
                    "error": "User is already verified",
                    "verified_via": profile.verified_via,
                    "verified_at": profile.verified_at,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        notes = request.data.get("notes", "")

        profile.verify_user(verified_via="admin", verified_by=request.user, notes=notes)

        logger.info(f"Admin {request.user.email} verified user {profile.user.email}")

        return Response(
            {
                "success": True,
                "message": "User verified successfully",
                "verification_status": profile.get_verification_status(),
            }
        )


class AdminUnverifyUserAPI(APIView):
    """
    Remove user verification (Admin only).

    POST /api/admin/users/{uuid}/unverify/

    This removes the verified status from a user.
    """

    permission_classes = [IsAuthenticated, IsAdmin]

    @swagger_auto_schema(
        tags=["Admin"],
        operation_description="Remove user verification (Admin only)",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            required=["reason"],
            properties={
                "reason": openapi.Schema(
                    type=openapi.TYPE_STRING,
                    description="Reason for removing verification",
                )
            },
        ),
        responses={
            200: openapi.Response(
                description="Verification removed",
                examples={
                    "application/json": {
                        "success": True,
                        "message": "User verification removed",
                        "verification_status": {
                            "is_verified": False,
                            "verified_via": None,
                        },
                    }
                },
            ),
            400: "User is not verified or reason not provided",
            404: "User not found",
        },
    )
    def post(self, request, user_id):
        """Remove user verification."""
        try:
            profile = UserProfile.objects.get(public_id=user_id)
        except UserProfile.DoesNotExist:
            return Response(
                {"error": "User not found"}, status=status.HTTP_404_NOT_FOUND
            )

        if not profile.is_verified_user:
            return Response(
                {"error": "User is not verified"}, status=status.HTTP_400_BAD_REQUEST
            )

        reason = request.data.get("reason", "")
        if not reason:
            return Response(
                {"error": "Reason is required for removing verification"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        old_verified_via = profile.verified_via
        profile.unverify_user(admin_user=request.user, notes=reason)

        logger.info(
            f"Admin {request.user.email} removed verification from user {profile.user.email} "
            f"(was: {old_verified_via})"
        )

        return Response(
            {
                "success": True,
                "message": "User verification removed",
                "verification_status": profile.get_verification_status(),
            }
        )


class AdminUserVerificationDetailAPI(APIView):
    """
    Get detailed verification info for a user (Admin only).

    GET /api/admin/users/{uuid}/verification/

    Returns full verification details including LinkedIn data.
    """

    permission_classes = [IsAuthenticated, IsAdmin]

    @swagger_auto_schema(
        tags=["Admin"],
        operation_description="Get user verification details (Admin only)",
        responses={200: "Verification details", 404: "User not found"},
    )
    def get(self, request, user_id):
        """Get verification details for a user."""
        from .serializers import UserVerificationSerializer

        try:
            profile = UserProfile.objects.select_related("verified_by").get(
                public_id=user_id
            )
        except UserProfile.DoesNotExist:
            return Response(
                {"error": "User not found"}, status=status.HTTP_404_NOT_FOUND
            )

        serializer = UserVerificationSerializer(profile)
        return Response(
            {
                "user_email": profile.user.email,
                "user_name": profile.name,
                **serializer.data,
            }
        )
