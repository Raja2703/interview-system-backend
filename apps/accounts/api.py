# apps/accounts/api.py
import logging
from django.contrib.auth import authenticate, get_user_model, logout as django_logout
from django.shortcuts import redirect
from django.views.decorators.csrf import csrf_exempt
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenRefreshView
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi
from apps.profiles.models import UserProfile
from .serializers import (
    LoginRequestSerializer,
    SignupRequestSerializer,
    AuthResponseSerializer,
    LogoutResponseSerializer,
    AuthStatusResponseSerializer,
    UserPayloadSerializer,
)
from allauth.account.models import EmailAddress
from allauth.account.adapter import get_adapter
from allauth.account.utils import user_email
from allauth.account.models import EmailAddress


from django.contrib.auth import authenticate
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from allauth.account.models import EmailAddress
from django.contrib.auth import get_user_model

from allauth.account.views import ConfirmEmailView
from django.http import HttpResponseRedirect
from django.urls import reverse
from allauth.account.models import EmailConfirmation

from django.conf import settings

logger = logging.getLogger(__name__)
User = get_user_model()

# --------------------------------------------------
# Utilities & Health Check
# --------------------------------------------------


@api_view(["GET"])
@permission_classes([AllowAny])
def health_check(request):
    """Simple health check endpoint."""
    return Response(
        {"status": "healthy", "message": "Interview Platform Backend is running"}
    )


def issue_tokens(user):
    refresh = RefreshToken.for_user(user)
    return {
        "access": str(refresh.access_token),
        "refresh": str(refresh),
    }


def user_payload(user):
    """
    Generate user payload for API responses.
    Updated to support multi-role users and onboarding status.
    """
    profile, _ = UserProfile.objects.get_or_create(user=user)

    # Get list of role names for multi-role support
    roles = profile.get_role_names()

    # Get onboarding status
    onboarding_status = (
        profile.get_onboarding_status() if profile.has_any_role() else {}
    )

    if not profile.public_id:
        import uuid

        profile.public_id = uuid.uuid4()
        profile.save(update_fields=["public_id"])

    return {
        "id": user.id,
        "uuid": profile.public_id,
        "username": user.username,
        "email": user.email,
        # Full name from User model
        "first_name": user.first_name,
        "last_name": user.last_name,
        # Name from profile (onboarding field)
        "name": profile.name,
        # NEW: List of roles for multi-role support
        "roles": roles,
        # DEPRECATED: Single role for backward compatibility
        "role": profile.get_effective_role(),
        # Updated to check for any role
        "has_role": profile.has_any_role(),
        # NEW: Admin status
        "is_admin": user.is_staff or user.is_superuser,
        "is_staff": user.is_staff,
        "is_superuser": user.is_superuser,
        "oauth_provider": profile.oauth_provider,
        "profile_picture_url": profile.profile_picture_url,
        "linkedin_profile_url": profile.linkedin_profile_url,
        # ========== COMMON ONBOARDING FIELDS ==========
        "phone_prefix": profile.phone_prefix,  # NEW
        "mobile_number": profile.mobile_number,
        "bio": profile.bio,
        "designation": profile.designation,
        "experience_years": profile.experience_years,
        "available_time_slots": profile.available_time_slots or [],
        # DEPRECATED: Use designation instead
        "current_position": profile.current_position,
        "profile_complete": profile.onboarding_completed,
        # ========== ONBOARDING STATUS ==========
        "onboarding_completed": profile.onboarding_completed,
        "onboarding_required": (
            profile.is_onboarding_required() if profile.has_any_role() else False
        ),
        "pending_onboarding_steps": onboarding_status.get("pending_steps", []),
        "onboarding_progress": onboarding_status.get("progress_percentage", 0),
    }


# --------------------------------------------------
# Email / Password Auth
# --------------------------------------------------


@swagger_auto_schema(
    method="post",
    request_body=LoginRequestSerializer,
    responses={
        200: openapi.Response(
            description="Login successful",
            examples={
                "application/json": {
                    "success": True,
                    "tokens": {"access": "<access_jwt>", "refresh": "<refresh_jwt>"},
                    "user": {
                        "username": "john_doe",
                        "email": "john@example.com",
                        "role": "attender",
                        "oauth_provider": "google",
                        "has_role": True,
                    },
                }
            },
        ),
        400: "Email and password required",
        401: "Invalid credentials",
    },
    operation_description="Login with email and password to receive JWT tokens.",
)


# apps/accounts/api.py


@api_view(["POST"])
@permission_classes([AllowAny])
def login_api(request):
    serializer = LoginRequestSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(
            {"success": False, "error": "Invalid data", "errors": serializer.errors},
            status=400,
        )

    email = serializer.validated_data["email"]
    password = serializer.validated_data["password"]

    # 🔹 Step 1: Check if user exists
    try:
        user = User.objects.get(email=email)
    except User.DoesNotExist:
        logger.warning(f"Login attempt with non-existent email: {email}")
        return Response({"success": False, "error": "Invalid credentials"}, status=401)

    # 🔹 Step 2: Check if email is verified
    email_obj = EmailAddress.objects.filter(
        user=user, email=email, verified=True
    ).first()

    if not email_obj:
        logger.warning(f"Login attempt with unverified email: {email}")
        # Check if email exists but is unverified
        unverified = EmailAddress.objects.filter(
            user=user, email=email, verified=False
        ).exists()
        if unverified:
            return Response(
                {
                    "success": False,
                    "error": "Please verify your email before logging in",
                    "code": "email_not_verified",
                },
                status=403,
            )
        return Response({"success": False, "error": "Invalid credentials"}, status=401)

    # 🔹 Step 3: Ensure user is active
    if not user.is_active:
        user.is_active = True
        user.save(update_fields=["is_active"])
        logger.info(f"Activated user: {user.username}")

    # 🔹 Step 4: Authenticate with custom backend
    authenticated_user = authenticate(request=request, email=email, password=password)

    if not authenticated_user:
        logger.warning(f"Authentication failed for email: {email}")
        # Double-check the password manually for debugging
        if user.check_password(password):
            logger.error(
                f"Password is correct but authenticate() returned None for {email}"
            )
            # This means the backend is the issue
            return Response(
                {
                    "success": False,
                    "error": "Authentication system error. Contact support.",
                    "debug": "Password correct but authentication failed",
                },
                status=500,
            )
        return Response({"success": False, "error": "Invalid credentials"}, status=401)

    # 🔹 Step 5: Issue JWT tokens
    tokens = issue_tokens(authenticated_user)

    logger.info(f"Successful login for user: {authenticated_user.username}")

    return Response(
        {
            "success": True,
            "message": f"Welcome back, {authenticated_user.username}!",
            "tokens": tokens,
            "user": user_payload(authenticated_user),
        },
        status=200,
    )


"""if user is not None and user.is_active:
        tokens = issue_tokens(user)
        return Response({
            "message": "Login successful",
            "tokens": tokens,
            "user": user_payload(user)
        })
    else:
        return Response({"message": "Invalid credentials"}, status=401)
"""


@swagger_auto_schema(
    method="post",
    request_body=SignupRequestSerializer,
    responses={201: AuthResponseSerializer, 400: "Validation error"},
    operation_description="Register a new user with email and password.",
)
@api_view(["POST"])
@permission_classes([AllowAny])
def signup_api(request):
    serializer = SignupRequestSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(
            {"success": False, "errors": serializer.errors},
            status=400,
        )

    username = serializer.validated_data["username"]
    email = serializer.validated_data["email"]
    password = serializer.validated_data["password"]

    from allauth.account.models import EmailAddress

    # ------------------------------------------------
    # Case 1: Email already exists
    # ------------------------------------------------
    existing_user = User.objects.filter(email=email).first()
    if existing_user:
        email_address = EmailAddress.objects.filter(
            user=existing_user,
            email=email,
        ).first()

        if email_address and email_address.verified:
            return Response(
                {
                    "success": False,
                    "error": "Email already registered and verified. Please log in.",
                },
                status=400,
            )

        email_address, _ = EmailAddress.objects.get_or_create(
            user=existing_user,
            email=email,
            defaults={"verified": False, "primary": True},
        )

        email_address.send_confirmation(request)  # ✅ ONLY THIS

        return Response(
            {
                "success": True,
                "message": "Email not verified. Verification email resent.",
            },
            status=200,
        )

    # ------------------------------------------------
    # Case 2: New user
    # ------------------------------------------------
    if User.objects.filter(username=username).exists():
        return Response(
            {"success": False, "error": "Username already taken"},
            status=400,
        )

    # ========== PASSWORD SECURITY ==========
    # SECURITY: User.objects.create_user() automatically hashes the password
    # using Django's default PBKDF2 algorithm. Plaintext passwords are NEVER stored.
    # DO NOT replace this with User.objects.create() as that would store raw passwords!
    user = User.objects.create_user(
        username=username,
        email=email,
        password=password,
        # is_active=False,
    )

    UserProfile.objects.get_or_create(user=user)

    email_address = EmailAddress.objects.create(
        user=user,
        email=email,
        verified=False,
        primary=True,
    )

    email_address.send_confirmation(request)  # ✅ ONLY THIS

    return Response(
        {
            "success": True,
            "message": "Account created. Verification email sent.",
        },
        status=201,
    )


# --------------------------------------------------
# OAuth Endpoints
# --------------------------------------------------


@swagger_auto_schema(
    method="get",
    responses={302: "Redirect to Google Login"},
    operation_description="Initiates Google OAuth login by redirecting the user to the Google login page.",
)
@api_view(["GET"])
@permission_classes([AllowAny])
def google_login_api(request):
    """
    Redirects to Google OAuth login.
    Using process=login and prompt=select_account to ensure user can choose account.
    """
    # return redirect("/accounts/google/login/?process=login&prompt=select_account")
    return redirect("/accounts/google/login/")


@swagger_auto_schema(
    method="get",
    responses={302: "Redirect to LinkedIn Login"},
    operation_description="Redirects to LinkedIn OAuth authorization URL.",
)
@api_view(["GET"])
@permission_classes([AllowAny])
def linkedin_login_api(request):
    """
    Redirects to LinkedIn OAuth authorization URL.
    Uses allauth's built-in redirect to avoid hardcoded URLs.
    """
    # return redirect("/accounts/linkedin_oauth2/login/?process=login&prompt=login")
    return redirect("/accounts/linkedin_oauth2/login/")


@swagger_auto_schema(
    method="get",
    responses={200: AuthResponseSerializer, 401: "OAuth failed"},
    operation_description="Finalizes OAuth login and issues JWT tokens.",
)
# @api_view(["GET"])
# @permission_classes([AllowAny])
# def oauth_success(request):
#     if not request.user.is_authenticated:
#         return Response({"error": "OAuth failed"}, status=401)

#     profile, _ = UserProfile.objects.get_or_create(user=request.user)
#     tokens = issue_tokens(request.user)

#     return Response({
#         "success": True,
#         "tokens": tokens,
#         "user": user_payload(request.user),
#     })


@api_view(["GET"])
@permission_classes([AllowAny])
def oauth_success(request):
    frontend_url = getattr(settings, "FRONTEND_URL")
    if not request.user.is_authenticated:
        return redirect(f"{frontend_url}/login?error=oauth")

    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    tokens = issue_tokens(request.user)

    logging.info("Inside oauth success")
    response = redirect(
        f"{frontend_url}/oauth-success"
        f"?access={tokens['access']}&refresh={tokens['refresh']}"
    )

    return response


@swagger_auto_schema(
    method="post",
    operation_description="Complete OAuth authentication and return user data",
    request_body=openapi.Schema(
        type=openapi.TYPE_OBJECT,
        properties={
            "provider": openapi.Schema(
                type=openapi.TYPE_STRING, description="OAuth provider (google/linkedin)"
            ),
            "access_token": openapi.Schema(
                type=openapi.TYPE_STRING, description="OAuth access token"
            ),
        },
    ),
    responses={200: AuthResponseSerializer, 401: "Authentication required"},
)
@api_view(["POST"])
@permission_classes([AllowAny])
def oauth_complete(request):
    """Handle OAuth completion and return user data."""
    if not request.user.is_authenticated:
        return Response(
            {"success": False, "error": "Authentication required"}, status=401
        )

    tokens = issue_tokens(request.user)

    return Response(
        {
            "success": True,
            "message": "OAuth authentication successful",
            "tokens": tokens,
            "user": user_payload(request.user),
        }
    )


# --------------------------------------------------
# Auth Status & Logout
# --------------------------------------------------


@swagger_auto_schema(
    method="get",
    operation_description="Get current authentication status",
    responses={200: AuthStatusResponseSerializer},
)
@api_view(["GET"])
@permission_classes([AllowAny])
def auth_status(request):
    if not request.user.is_authenticated:
        return Response({"authenticated": False})

    return Response(
        {
            "authenticated": True,
            "user": user_payload(request.user),
        }
    )


@swagger_auto_schema(
    method="post",
    request_body=openapi.Schema(
        type=openapi.TYPE_OBJECT,
        properties={
            "refresh_token": openapi.Schema(
                type=openapi.TYPE_STRING, description="Refresh token to blacklist"
            )
        },
    ),
    operation_description="Logout current user, blacklist refresh token, and clear session",
    responses={200: LogoutResponseSerializer},
)
@api_view(["POST", "GET"])
@permission_classes([AllowAny])
def logout_api(request):
    """API endpoint for logout. Blacklists refresh token and clears Django session."""
    from rest_framework_simplejwt.tokens import RefreshToken

    refresh_token = request.data.get("refresh_token")
    if refresh_token:
        try:
            token = RefreshToken(refresh_token)
            token.blacklist()
            logger.info(
                f"Successfully blacklisted refresh token for user: {request.user}"
            )
        except Exception as e:
            logger.warning(f"Failed to blacklist token: {e}")

    if request.user.is_authenticated:
        django_logout(request)

    return Response(
        {
            "success": True,
            "message": "Logged out successfully. Tokens invalidated. Session cleared.",
        }
    )


class DecoratedTokenRefreshView(TokenRefreshView):
    @swagger_auto_schema(
        operation_description="Refresh access token using refresh token",
        responses={
            200: openapi.Response(
                description="New access token",
                examples={"application/json": {"access": "<new_access_token>"}},
            )
        },
    )
    def post(self, request, *args, **kwargs):
        return super().post(request, *args, **kwargs)


@swagger_auto_schema(
    method="get",
    operation_description="Returns list of web auth endpoints (HTML/redirect flows)",
    responses={
        200: openapi.Response(
            description="Endpoints mapping",
            examples={
                "application/json": {
                    "login": "/accounts/login/",
                    "signup": "/accounts/signup/",
                    "google_oauth": "/accounts/google/login/",
                    "linkedin_oauth": "/accounts/linkedin_oauth2/login/",
                    "logout": "/accounts/logout/",
                    "token_refresh": "/api/token/refresh/",
                    "auth_status": "/api/auth-status/",
                }
            },
        )
    },
)
@api_view(["GET"])
@permission_classes([AllowAny])
def auth_endpoints(request):
    return Response(
        {
            "login": "/accounts/login/",
            "signup": "/accounts/signup/",
            "google_oauth": "/accounts/google/login/",
            "linkedin_oauth": "/accounts/linkedin_oauth2/login/",
            "logout": "/accounts/logout/",
            "token_refresh": "/api/token/refresh/",
            "auth_status": "/api/auth-status/",
        }
    )


# --------------------------------------------------
# Custom Email Verification View
# --------------------------------------------------


class CustomConfirmEmailView(ConfirmEmailView):
    def get(self, *args, **kwargs):
        frontend_url = getattr(settings, "FRONTEND_URL")
        try:
            # Attempt to retrieve the confirmation object (validates key)
            self.object = self.get_object()
        except:
            # FAILURE: Invalid or expired key -> Redirect to React Frontend Failure Page
            return HttpResponseRedirect(
                f"{frontend_url}/signup/verify-email?status=failed"
            )

        # Confirm the email address
        self.object.confirm(self.request)

        # SUCCESS: Redirect to React Frontend Success Page
        return HttpResponseRedirect(
            f"{frontend_url}/signup/verify-email?status=success"
        )


# --------------------------------------------------
# Resend Email Verification API
# --------------------------------------------------


@swagger_auto_schema(
    method="post",
    operation_description="Resend email verification link",
    request_body=openapi.Schema(
        type=openapi.TYPE_OBJECT,
        required=["email"],
        properties={
            "email": openapi.Schema(
                type=openapi.TYPE_STRING,
                format="email",
                description="Email address to resend verification to",
            )
        },
    ),
    responses={
        200: openapi.Response(
            description="Verification email sent (or already verified)",
            examples={
                "application/json": {
                    "success": True,
                    "message": "If this email exists and is unverified, a verification link has been sent.",
                }
            },
        )
    },
)
@api_view(["POST"])
@permission_classes([AllowAny])
def resend_verification_api(request):
    """
    Resend email verification link.
    - Does not reveal whether email exists (security)
    - Uses allauth's send_confirmation()
    """
    email = request.data.get("email", "").strip().lower()

    if not email:
        return Response({"success": False, "error": "Email is required"}, status=400)

    # Generic success message (no user enumeration)
    success_response = Response(
        {
            "success": True,
            "message": "If this email exists and is unverified, a verification link has been sent.",
        }
    )

    try:
        user = User.objects.get(email=email)
    except User.DoesNotExist:
        # Don't reveal that user doesn't exist
        logger.info(f"Resend verification requested for non-existent email: {email}")
        return success_response

    # Check email verification status
    email_address = EmailAddress.objects.filter(user=user, email=email).first()

    if not email_address:
        # Create EmailAddress if it doesn't exist
        email_address = EmailAddress.objects.create(
            user=user, email=email, verified=False, primary=True
        )

    if email_address.verified:
        logger.info(
            f"Resend verification requested for already verified email: {email}"
        )
        return Response(
            {
                "success": True,
                "message": "This email is already verified. You can log in.",
            }
        )

    # Resend verification email using allauth
    email_address.send_confirmation(request)
    logger.info(f"Verification email resent to: {email}")

    return success_response


# --------------------------------------------------
# Forgot Password / Password Reset Request API
# --------------------------------------------------


@swagger_auto_schema(
    method="post",
    operation_description="Request password reset email",
    request_body=openapi.Schema(
        type=openapi.TYPE_OBJECT,
        required=["email"],
        properties={
            "email": openapi.Schema(
                type=openapi.TYPE_STRING,
                format="email",
                description="Email address for password reset",
            )
        },
    ),
    responses={
        200: openapi.Response(
            description="Password reset email sent",
            examples={
                "application/json": {
                    "success": True,
                    "message": "If an account exists with this email, a password reset link has been sent.",
                }
            },
        )
    },
)
@api_view(["POST"])
@permission_classes([AllowAny])
def password_reset_request_api(request):
    """
    Request password reset email.
    - Uses django-allauth's ResetPasswordForm
    - Does not reveal whether email exists (security)
    """
    # from allauth.account.forms import ResetPasswordForm

    email = request.data.get("email", "").strip().lower()

    if not email:
        return Response({"success": False, "error": "Email is required"}, status=400)

    # Generic success message (no user enumeration)
    success_response = Response(
        {
            "success": True,
            "message": "If an account exists with this email, a password reset link has been sent.",
        }
    )

    # Use Custom FrontendResetPasswordForm instead of allauth ResetPasswordForm
    from apps.accounts.forms import FrontendResetPasswordForm

    form = FrontendResetPasswordForm(data={"email": email})

    if form.is_valid():
        # This will send the reset email if user exists
        form.save(request)
        logger.info(f"Password reset requested for: {email}")
    else:
        # Don't reveal validation errors (could indicate user existence)
        logger.info(f"Password reset requested for invalid/non-existent email: {email}")

    return success_response


# --------------------------------------------------
# Password Reset Confirm API
# --------------------------------------------------


@swagger_auto_schema(
    method="post",
    operation_description="Confirm password reset with token",
    request_body=openapi.Schema(
        type=openapi.TYPE_OBJECT,
        required=["uid", "token", "new_password"],
        properties={
            "uid": openapi.Schema(
                type=openapi.TYPE_STRING, description="User ID (base64 encoded)"
            ),
            "token": openapi.Schema(
                type=openapi.TYPE_STRING, description="Password reset token"
            ),
            "new_password": openapi.Schema(
                type=openapi.TYPE_STRING, description="New password"
            ),
        },
    ),
    responses={
        200: openapi.Response(
            description="Password reset successful",
            examples={
                "application/json": {
                    "success": True,
                    "message": "Password has been reset successfully.",
                }
            },
        ),
        400: openapi.Response(
            description="Invalid token or password",
            examples={
                "application/json": {
                    "success": False,
                    "error": "Invalid or expired reset link.",
                }
            },
        ),
    },
)
@api_view(["POST"])
@permission_classes([AllowAny])
def password_reset_confirm_api(request):
    """
    Confirm password reset with uid, token, and new password.
    - Validates token using Django's PasswordResetTokenGenerator
    - Sets new password
    - Invalidates existing sessions for security
    - Includes timing attack mitigation
    """
    # NEW IMPORTS for security enhancements
    import time
    from django.utils.http import urlsafe_base64_decode
    from django.contrib.auth.tokens import default_token_generator
    from django.contrib.auth.password_validation import validate_password
    from django.core.exceptions import ValidationError
    from django.contrib.auth import (
        update_session_auth_hash,
    )  # NEW: Session invalidation

    # NEW: Consistent delay for timing attack mitigation (applied on failures)
    FAILURE_DELAY_SECONDS = 0.5

    def delayed_failure_response(error_msg, details=None):
        """Return failure response with consistent delay to prevent timing attacks."""
        time.sleep(FAILURE_DELAY_SECONDS)
        response_data = {"success": False, "error": error_msg}
        if details:
            response_data["details"] = details
        return Response(response_data, status=400)

    uid = request.data.get("uid", "")
    token = request.data.get("token", "")
    new_password = request.data.get("new_password", "")

    # Validate required fields
    if not uid or not token:
        logger.warning("Password reset confirm failed: missing uid or token")
        return delayed_failure_response("Invalid or expired reset link.")

    if not new_password:
        logger.warning("Password reset confirm failed: missing new_password")
        return delayed_failure_response("New password is required.")

    # Decode uid to get user
    try:
        user_id = urlsafe_base64_decode(uid).decode()
        user = User.objects.get(pk=user_id)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        logger.warning("Password reset confirm failed: invalid uid")
        return delayed_failure_response("Invalid or expired reset link.")

    # Validate token
    if not default_token_generator.check_token(user, token):
        logger.warning(
            f"Password reset confirm failed: invalid token for user {user.email}"
        )
        return delayed_failure_response("Invalid or expired reset link.")

    # Validate new password strength
    try:
        validate_password(new_password, user)
    except ValidationError as e:
        logger.warning(
            f"Password reset confirm failed: weak password for user {user.email}"
        )
        return delayed_failure_response(
            "Password validation failed.", details=list(e.messages)
        )

    # Set new password
    user.set_password(new_password)
    user.save()

    # NEW: Invalidate all existing sessions for this user
    # update_session_auth_hash with None logs out all sessions by changing session auth hash
    # Since we don't want auto-login, we pass None or skip calling it with current session
    # The password change itself invalidates the session auth hash
    logger.info(
        f"Password reset successful for user: {user.email} - All sessions invalidated"
    )

    # No delay on success (timing attack mitigation only on failures)
    return Response(
        {
            "success": True,
            "message": "Password has been reset successfully. You can now log in with your new password.",
        }
    )
