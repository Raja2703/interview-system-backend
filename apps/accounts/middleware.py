# apps/accounts/middleware.py

import logging
from django.shortcuts import redirect
from django.http import JsonResponse
from django.conf import settings
from django.utils.deprecation import MiddlewareMixin
from apps.profiles.models import UserProfile
from django.db import DatabaseError
import environ
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env()
environ.Env.read_env(BASE_DIR / ".env")

FRONTEND_URL = env("FRONTEND_URL")

logger = logging.getLogger(__name__)


class RoleRequiredMiddleware(MiddlewareMixin):
    """
    Middleware to enforce role selection and onboarding completion for authenticated users.
    
    Flow:
        1. Allow exempt paths/prefixes
        2. Check authentication
        3. Enforce role selection
        4. Enforce onboarding completion (NEW)
    """

    EXEMPT_PREFIXES = (
        "/accounts/",
        "/admin/",
        "/static/",
        "/media/",
        "/api/auth/",
        "/api/oauth-complete/",
        "/api/select-role/",  # Allow select-role endpoint
        "/api/onboarding/",   # Allow onboarding endpoints
        "/api/profile/",
        "/api/auth-status/",
        "/api/auth-endpoints/",
        "/api/enums/",        # NEW: Enum API (no auth required)
        "/api/admin/",        # NEW: Admin APIs (have own permission checks)
        "/swagger/",
        "/redoc/",
        "/swagger.json",
        "/api/docs/",
    )

    # Root URL should not be redirected by middleware - it handles its own logic
    EXEMPT_PATHS = (
        "/",
        "/api/",  # API root endpoint
    )

    MAX_REDIRECTS = 3
    REDIRECT_COUNT_KEY = "role_redirect_count"

    def process_request(self, request):
        path = request.path_info
        logger.debug(f"[RoleMiddleware] Checking path: {path}")

        # Allow exempt paths (exact match first for efficiency)
        if path in self.EXEMPT_PATHS:
            logger.debug(f"[RoleMiddleware] Path is exempt (exact): {path}")
            return None

        # Allow exempt prefixes
        for exempt_prefix in self.EXEMPT_PREFIXES:
            if path.startswith(exempt_prefix):
                logger.debug(f"[RoleMiddleware] Path is exempt (prefix): {path}")
                return None

        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            logger.debug(f"[RoleMiddleware] User not authenticated, skipping: {path}")
            return None

        # ========== ADMIN BYPASS (NEW) ==========
        # Admins (is_staff or is_superuser) bypass role and onboarding checks
        if user.is_staff or user.is_superuser:
            logger.debug(f"[RoleMiddleware] Admin user {user.email} bypassing checks for: {path}")
            return None

        # Check redirect loop prevention
        redirect_count = request.session.get(self.REDIRECT_COUNT_KEY, 0)
        if redirect_count >= self.MAX_REDIRECTS:
            logger.error(
                f"[RoleMiddleware] Redirect loop detected for user {user.email}"
            )
            request.session[self.REDIRECT_COUNT_KEY] = 0

            # Get frontend URL from settings with fallback
            frontend_url = getattr(settings, "FRONTEND_URL", FRONTEND_URL)

            return JsonResponse(
                {
                    "error": "Redirect loop detected. Please contact support.",
                    "redirect_url": f"{frontend_url}/select-role/",
                    "status": "error",
                },
                status=400,
            )

        try:
            profile = UserProfile.objects.filter(user=user).first()
            if profile is None:
                profile = UserProfile.objects.create(user=user)
                logger.info(
                    f"[RoleMiddleware] Created missing profile for user {user.email}"
                )

            # ========== STEP 1: Check for role selection ==========
            # This supports multi-role: user is allowed if they have any role assigned
            if not profile.has_any_role():
                request.session[self.REDIRECT_COUNT_KEY] = redirect_count + 1
                logger.info(
                    f"[RoleMiddleware] User {user.email} needs role selection (count: {redirect_count + 1})"
                )

                # For API endpoints, return JSON instead of redirect
                if path.startswith("/api/") or path.startswith("/dashboard/"):
                    logger.info(
                        f"[RoleMiddleware] Returning 403 Role Required for API: {path}"
                    )
                    return JsonResponse(
                        {
                            "error": "Role selection required",
                            "message": "Please select your role(s) before accessing this endpoint",
                            "redirect_url": "/api/select-role/",
                            "status": "role_required",
                        },
                        status=403,
                    )
                else:
                    # For web requests, redirect to frontend select-role page
                    frontend_url = getattr(settings, "FRONTEND_URL", FRONTEND_URL)
                    redirect_url = f"{frontend_url}/select-role/"
                    logger.info(
                        f"[RoleMiddleware] Redirecting web user to: {redirect_url}"
                    )
                    return redirect(redirect_url)

            # ========== STEP 2: Check for onboarding completion (NEW) ==========
            # Onboarding is required AFTER role selection
            if profile.is_onboarding_required():
                request.session[self.REDIRECT_COUNT_KEY] = redirect_count + 1
                logger.info(
                    f"[RoleMiddleware] User {user.email} needs onboarding completion (count: {redirect_count + 1})"
                )
                
                # Get onboarding status for response
                onboarding_status = profile.get_onboarding_status()
                
                # For API endpoints, return JSON instead of redirect
                if path.startswith("/api/") or path.startswith("/dashboard/"):
                    logger.info(
                        f"[RoleMiddleware] Returning 403 Onboarding Required for API: {path}"
                    )
                    return JsonResponse(
                        {
                            "error": "Onboarding required",
                            "message": "Please complete your profile onboarding before accessing this endpoint",
                            "redirect_url": "/api/onboarding/status/",
                            "status": "onboarding_required",
                            "onboarding_status": onboarding_status,
                        },
                        status=403,
                    )
                else:
                    # For web requests, redirect to frontend onboarding page
                    frontend_url = getattr(settings, "FRONTEND_URL", FRONTEND_URL)
                    redirect_url = f"{frontend_url}/onboarding/"
                    logger.info(
                        f"[RoleMiddleware] Redirecting web user to onboarding: {redirect_url}"
                    )
                    return redirect(redirect_url)

            # Reset redirect count on successful checks
            if redirect_count > 0:
                logger.debug(
                    f"[RoleMiddleware] Resetting redirect count for {user.email}"
                )
                request.session[self.REDIRECT_COUNT_KEY] = 0

            # UPDATED: Log all user roles instead of single role
            user_roles = profile.get_role_names()
            logger.debug(
                f"[RoleMiddleware] User {user.email} has roles {user_roles}, onboarding complete, allowing: {path}"
            )

        except DatabaseError as e:
            logger.error(f"Database error in RoleRequiredMiddleware: {e}")
            return None
        except Exception as e:
            logger.error(
                f"Unexpected error in RoleRequiredMiddleware: {e}", exc_info=True
            )
            return None

        return None
