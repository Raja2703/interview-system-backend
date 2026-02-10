#apps/profiles/views.py
from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.authentication import TokenAuthentication
from rest_framework_simplejwt.authentication import JWTAuthentication

from .models import UserProfile
import logging

logger = logging.getLogger(__name__)

AVAILABLE_ROLES = [
    {
        "name": "interviewee",
        "label": "Interviewee",
        "description": "Can attend interviews"
    },
    {
        "name": "interviewer",
        "label": "Interviewer",
        "description": "Can conduct interviews"
    },
    {
        "name": "both",
        "label": "Interviewee + Interviewer",
        "description": "Can attend and conduct interviews"
    },
]


@api_view(["GET", "POST"])
@authentication_classes([JWTAuthentication])  # 🔑 disables CSRF
@permission_classes([IsAuthenticated])
def select_role_view(request):
    user = request.user

    profile, _ = UserProfile.objects.get_or_create(user=user)

    # GET → onboarding info
    if request.method == "GET":
        return Response({
            "authenticated": True,
            "email": user.email,
            "current_role": profile.role,
            "has_role": bool(profile.role),
            "available_roles": AVAILABLE_ROLES,
            "next_step": (
                "select_role" if not profile.role else "complete_profile"
            )
        })

    # POST → set role
    role_name = request.data.get("role")

    if not role_name:
        return Response({"error": "role is required"}, status=400)

    valid_roles = [r["name"] for r in AVAILABLE_ROLES]
    if role_name not in valid_roles:
        return Response(
            {"error": f"Invalid role. Choose one of {valid_roles}"},
            status=400
        )

    profile.role = role_name
    profile.save()

    logger.info(f"{user.email} selected role {role_name}")

    return Response({
        "success": True,
        "role": role_name,
        "message": "Role selected successfully",
        "next_step": "complete_profile"
    })
