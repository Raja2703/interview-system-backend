# apps/common/api.py
"""
API endpoints for common functionality.
"""

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi

from .enums import get_all_enums


@swagger_auto_schema(
    method='get',
    tags=["Enums"],
    operation_description="""
    Get all application constants/enums.
    
    This endpoint returns read-only constants used across the platform for:
    - Phone prefixes
    - Designation options
    - Skills
    - Languages
    - Target roles
    - Career goals
    - Expertise levels
    - User roles
    - Experience years range
    - Days of week
    
    **No authentication required.**
    """,
    responses={
        200: openapi.Response(
            description="All enums and constants",
            examples={
                "application/json": {
                    "phone_prefixes": [
                        {"code": "+91", "country": "India"},
                        {"code": "+1", "country": "United States"}
                    ],
                    "designation_options": ["Software Developer", "Backend Developer"],
                    "skills": ["Python", "JavaScript", "Java"],
                    "languages": ["English", "Hindi"],
                    "target_roles": ["Software Engineer", "Senior Software Engineer"],
                    "career_goals": [
                        {"value": "finding_jobs", "label": "Finding Jobs"}
                    ],
                    "expertise_levels": [
                        {"value": "beginner", "label": "Beginner"}
                    ],
                    "user_roles": [
                        {"value": "attender", "label": "Interview Attender"}
                    ],
                    "experience_years": {"min": 0, "max": 50, "default": 0},
                    "days_of_week": [
                        {"value": "monday", "label": "Monday"}
                    ]
                }
            }
        )
    }
)
@api_view(['GET'])
@permission_classes([AllowAny])
def enums_api(request):
    """
    Get all application constants/enums.
    
    Returns read-only constants used across onboarding and profiles.
    No authentication required.
    No database writes.
    """
    return Response(get_all_enums())
