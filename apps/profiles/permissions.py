from rest_framework.permissions import BasePermission
from apps.profiles.models import UserProfile


class RequireRole(BasePermission):
    message = "Role selection required to access this resource."

    def has_permission(self, request, view):
        user = request.user

        if not user or not user.is_authenticated:
            return False

        try:
            profile = user.profile
        except UserProfile.DoesNotExist:
            return False

        return bool(profile.role)
