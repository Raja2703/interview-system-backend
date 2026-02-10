# config/urls.py
from django.contrib import admin
from django.urls import path, include, re_path
from django.conf import settings
from django.conf.urls.static import static
from django.http import JsonResponse

from rest_framework import permissions
from drf_yasg.views import get_schema_view
from drf_yasg import openapi

from apps.accounts import api
from apps.accounts.views import verify_email_api
from apps.accounts import (
    linkedin_oidc_provider,
)  # CRITICAL: Import custom LinkedIn provider

from django.urls import re_path
from apps.accounts.api import CustomConfirmEmailView


def api_root(request):
    return JsonResponse({"status": "ok"})


schema_view = get_schema_view(
    openapi.Info(
        title="Interview Platform API",
        default_version="v1",
        description=(
            "Interview Platform Backend API\n\n"
            "## Authentication\n"
            "Most endpoints require JWT Bearer token authentication.\n\n"
            "### How to Authenticate:\n"
            "1. Call `POST /api/auth/login/` with email and password\n"
            "2. Copy the `access` token from the response\n"
            "3. Click the **Authorize** button (🔒) above\n"
            "4. Enter: `Bearer <your_access_token>` (include 'Bearer ' prefix!)\n"
            "5. Click Authorize, then Close\n\n"
            "---\n\n"
            "## Pagination\n"
            "All list endpoints support pagination with the following query parameters:\n\n"
            "| Parameter | Type | Default | Max | Description |\n"
            "|-----------|------|---------|-----|-------------|\n"
            "| `limit` | integer | 10 | 100 | Number of items to return |\n"
            "| `offset` | integer | 0 | - | Starting position in result set |\n\n"
            "### Example Requests:\n"
            "```\n"
            "GET /api/interviews/?limit=20          → First 20 items\n"
            "GET /api/interviews/?limit=20&offset=40 → Items 41-60\n"
            "GET /api/profiles/attender/?limit=50   → First 50 profiles\n"
            "```\n\n"
            "### Paginated Response Format:\n"
            "```json\n"
            "{\n"
            '  "count": 150,\n'
            '  "next": "...?limit=10&offset=20",\n'
            '  "previous": null,\n'
            '  "results": [...]\n'
            "}\n"
            "```\n\n"
            "---\n\n"
            "### Admin Access:\n"
            "Admin users (is_staff=True or is_superuser=True) have access to `/api/admin/*` endpoints.\n\n"
            "### Interview System:\n"
            "Interview requests and LiveKit room management available at `/api/interviews/*`."
        ),
    ),
    public=True,
    permission_classes=(permissions.AllowAny,),
    # CRITICAL FIX: Disable authentication for schema endpoint to prevent 401 errors
    authentication_classes=[],
)

urlpatterns = [
    path("", api_root),
    path("admin/", admin.site.urls),
    # -----------------------------
    # AUTH API (NO ALLAUTH SHADOW)
    # -----------------------------
    path("api/auth/login/", api.login_api),
    path("api/auth/signup/", api.signup_api),
    path("api/auth/logout/", api.logout_api),
    path("api/auth/token/refresh/", api.DecoratedTokenRefreshView.as_view()),
    # -----------------------------
    # EMAIL VERIFICATION (API)
    # -----------------------------
    re_path(
        r"^accounts/confirm-email/(?P<key>[-:\w]+)/$",
        CustomConfirmEmailView.as_view(),
        name="account_confirm_email",
    ),
    path("accounts/resend-verification/", api.resend_verification_api),
    # -----------------------------
    # PASSWORD RESET (API)
    # -----------------------------
    path("accounts/password/reset/", api.password_reset_request_api),
    path("accounts/password/reset/confirm/", api.password_reset_confirm_api),
    # -----------------------------
    # SOCIAL LOGIN
    # -----------------------------
    path("api/auth/google/login/", api.google_login_api),
    path("api/auth/linkedin/login/", api.linkedin_login_api),
    path("api/auth/oauth-success/", api.oauth_success, name="oauth_success"),
    # -----------------------------
    # CUSTOM LINKEDIN OAUTH HANDLERS
    # MUST COME BEFORE allauth.urls
    # -----------------------------
    path(
        "accounts/linkedin_oauth2/login/",
        linkedin_oidc_provider.oauth2_login,
        name="linkedin_oauth2_login",
    ),
    path(
        "accounts/linkedin_oauth2/login/callback/",
        linkedin_oidc_provider.oauth2_callback,
        name="linkedin_oauth2_callback",
    ),
    # -----------------------------
    # ALLAUTH (ONLY CALLBACKS & INTERNAL)
    # This will handle Google and other providers
    # LinkedIn is already handled above
    # -----------------------------
    path("accounts/", include("allauth.urls")),
    # -----------------------------
    # INTERVIEW SYSTEM APIs (NEW)
    # -----------------------------
    path("api/interviews/", include("apps.interviews.urls")),
    # -----------------------------
    # NOTIFICATION SYSTEM APIs
    # -----------------------------
    path("api/notifications/", include("apps.notifications.urls")),
    # -----------------------------
    # CREDITS SYSTEM APIs
    # -----------------------------
    path("api/credits/", include("apps.credits.urls")),
    # -----------------------------
    # OTHER APPS
    # -----------------------------
    path("api/", include("apps.profiles.urls")),
    # path("dashboard/", include("apps.interviews.urls")),
    # -----------------------------
    # DOCS
    # -----------------------------
    path("swagger/", schema_view.with_ui("swagger", cache_timeout=0)),
]

if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
