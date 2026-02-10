# apps/accounts/adapters.py
import logging
import uuid
from allauth.account.adapter import DefaultAccountAdapter
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.conf import settings
from apps.profiles.models import UserProfile
import environ
from pathlib import Path
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from django.contrib.auth.tokens import default_token_generator

BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env()
environ.Env.read_env(BASE_DIR / ".env")

FRONTEND_URL = env("FRONTEND_URL")

logger = logging.getLogger(__name__)


class CustomAccountAdapter(DefaultAccountAdapter):
    """
    Custom adapter for handling post-authentication redirects.
    Redirects users to auth-status to return JSON info.
    """

    def get_login_redirect_url(self, request):
        logger.info(f"OAuth login complete for {request.user.email}")
        return "/api/auth/oauth-success/"

    def get_signup_redirect_url(self, request):
        """Redirect to select-role after signup."""
        logger.info(f"User {request.user.email} signed up successfully")
        frontend_url = getattr(settings, "FRONTEND_URL", FRONTEND_URL)
        return f"{frontend_url}/select-role/"

    def populate_username(self, request, user):
        """
        Username is now required in signup form, no auto-generation needed.
        This method is kept for compatibility but doesn't modify username.
        """
        from allauth.account.utils import user_username, user_email

        email = user_email(user)
        username = user_username(user)

        # Username should already be provided by the form
        if username:
            logger.info(f"Username '{username}' provided for user with email {email}")
        else:
            logger.warning(f"No username provided for user with email {email}")

        return username

    def save_user(self, request, user, form, commit=True):
        """Save user and create associated profile."""
        # Username should be provided by the form, no need to populate
        user = super().save_user(request, user, form, commit)

        if commit:
            # Create user profile if it doesn't exist
            profile, created = UserProfile.objects.get_or_create(user=user)
            if created:
                logger.info(f"Created profile for user {user.email}")
        return user


class CustomSocialAccountAdapter(DefaultSocialAccountAdapter):
    """
    Custom adapter for handling OAuth authentication.

    IMPORTANT: LinkedIn verification for existing users is handled in pre_social_login()
    because save_user() is ONLY called for NEW user signups, not for existing users
    logging in via OAuth.

    Flow for EXISTING users with LinkedIn:
    1. pre_social_login() - Connect social account + trigger verification

    Flow for NEW users with LinkedIn:
    1. save_user() - Create user + profile + store LinkedIn data + verify
    """

    def get_login_redirect_url(self, request):
        """Return redirect based on role status."""
        if hasattr(request, "user") and request.user.is_authenticated:
            logger.info(f"User {request.user.email} logged in via OAuth")

        # If user has no role, redirect to select-role
        profile, _ = UserProfile.objects.get_or_create(user=request.user)
        if not profile.role:
            frontend_url = getattr(settings, "FRONTEND_URL", FRONTEND_URL)
            return f"{frontend_url}/select-role/"

        # For API-first approach, return to auth-status
        return "/api/auth-status/"

    def populate_user(self, request, sociallogin, data):
        """
        Populate user data from social login.
        Use exact name from OAuth provider for username.
        """
        user = super().populate_user(request, sociallogin, data)

        # Get name and email from social account data
        email = data.get("email", "")
        name = data.get("name", "")
        first_name = data.get("given_name", "") or data.get("first_name", "")
        last_name = data.get("family_name", "") or data.get("last_name", "")

        # Try to get the full name from various fields
        if not name and first_name:
            name = f"{first_name} {last_name}".strip() if last_name else first_name

        # Use the exact name as username, with fallback to email prefix
        if not user.username:
            if name:
                # Clean the name to make it a valid username
                username = self._clean_username_from_name(name)
                logger.info(
                    f"Using exact name '{name}' as username '{username}' for OAuth user {email}"
                )
            elif email:
                # Fallback to email prefix if no name available
                username = email.split("@")[0]
                logger.info(
                    f"Using email prefix '{username}' for OAuth user {email} (no name available)"
                )
            else:
                # Last resort fallback
                username = f"user_{uuid.uuid4().hex[:8]}"
                logger.info(
                    f"Generated random username '{username}' for OAuth user (no name or email)"
                )

            # Ensure uniqueness
            username = self._ensure_unique_username(username)
            user.username = username

        return user

    def _clean_username_from_name(self, name):
        """
        Clean a name to make it a valid username.
        Removes special characters and spaces, keeps only alphanumeric and basic chars.
        """
        import re

        # Replace spaces with underscores and remove special characters
        username = re.sub(r"[^\w\s-]", "", name.lower())
        username = re.sub(r"[\s-]+", "_", username)
        # Remove leading/trailing underscores
        username = username.strip("_")
        # Ensure it's not empty
        if not username:
            username = f"user_{uuid.uuid4().hex[:8]}"
        return username

    def _ensure_unique_username(self, base_username):
        """
        Ensure username is unique by appending numbers if needed.
        """
        from django.contrib.auth import get_user_model

        User = get_user_model()

        username = base_username
        counter = 1
        while User.objects.filter(username=username).exists():
            username = f"{base_username}_{counter}"
            counter += 1

        return username

    def _update_linkedin_profile_data(self, profile, user, extra_data):
        """
        Helper method to update LinkedIn profile data.
        Called from both save_user() and pre_social_login().

        Args:
            profile: UserProfile instance
            user: User instance
            extra_data: Dict of LinkedIn OAuth data

        Returns:
            bool: True if data was updated
        """
        profile.oauth_provider = "linkedin"

        # LinkedIn OpenID Connect data structure - extract comprehensive profile data
        if "picture" in extra_data:
            profile.profile_picture_url = extra_data["picture"]
        elif "pictureUrl" in extra_data:
            profile.profile_picture_url = extra_data["pictureUrl"]

        # Get LinkedIn ID
        if "sub" in extra_data:
            profile.linkedin_id = extra_data["sub"]
            if hasattr(user, "linkedin_id"):
                user.linkedin_id = extra_data["sub"]
                user.save(update_fields=["linkedin_id"])
        elif "id" in extra_data:
            profile.linkedin_id = extra_data["id"]
            if hasattr(user, "linkedin_id"):
                user.linkedin_id = extra_data["id"]
                user.save(update_fields=["linkedin_id"])

        # Get profile URL
        if "publicProfileUrl" in extra_data:
            profile.linkedin_profile_url = extra_data["publicProfileUrl"]
        elif "public_profile_url" in extra_data:
            profile.linkedin_profile_url = extra_data["public_profile_url"]

        # Get full name from LinkedIn
        name = extra_data.get("name", "")
        first_name = extra_data.get("given_name", "") or extra_data.get(
            "first_name", ""
        )
        last_name = extra_data.get("family_name", "") or extra_data.get("last_name", "")

        if not name and first_name:
            name = f"{first_name} {last_name}".strip() if last_name else first_name

        if name:
            profile.linkedin_full_name = name[:200]
            # Also set name if not already set
            if not profile.name:
                profile.name = name[:100]

        # Get headline
        if "headline" in extra_data:
            profile.linkedin_headline = extra_data["headline"][:300]
            # Also use as bio if not set
            if not profile.bio:
                profile.bio = extra_data["headline"][:500]

        # Current position/designation
        if "headline" in extra_data and not profile.designation:
            profile.designation = extra_data["headline"][:100]
            profile.current_position = extra_data["headline"][:100]
        elif "position" in extra_data:
            profile.designation = extra_data["position"][:100]
            profile.current_position = extra_data["position"][:100]

        # Company from LinkedIn (if available)
        if "company" in extra_data:
            profile.linkedin_company = extra_data["company"][:200]
            if not profile.company:
                profile.company = extra_data["company"][:150]

        # Store LinkedIn email (may differ from user's primary email)
        if "email" in extra_data:
            profile.linkedin_email = extra_data["email"]

        # Experience years - set default if not available
        if not profile.experience_years:
            profile.experience_years = 0

        return True

    def _trigger_linkedin_verification(self, profile, user, linkedin_email=None):
        """
        Trigger LinkedIn verification for taker role users.

        VERIFICATION RULES (per requirements):
        1. OAuth provider == "linkedin_oauth2" (or linkedin)
        2. LinkedIn email == existing user.email (if provided)
        3. User has role "taker" (Interviewer role)

        If verified:
        - profile.is_verified_user = True
        - profile.verified_via = "linkedin"
        - profile.verified_at = current timestamp

        Args:
            profile: UserProfile instance
            user: User instance
            linkedin_email: Email from LinkedIn OAuth

        Returns:
            tuple: (is_verified: bool, message: str)
        """
        # Skip if already verified
        if profile.is_verified_user:
            logger.debug(f"User {user.email} already verified, skipping")
            return True, "Already verified"

        # Check if user has taker role - ONLY takers can be auto-verified
        if not profile.is_taker():
            logger.debug(f"User {user.email} is not a taker, skipping verification")
            return False, "Verify your profile by signing in once via LinkedIn"

        # Check LinkedIn connection exists
        has_linkedin = profile.oauth_provider == "linkedin" or bool(profile.linkedin_id)

        if not has_linkedin:
            logger.debug(f"User {user.email} has no LinkedIn connection")
            return False, "Verify your profile by signing in once via LinkedIn"

        # OPTIONAL: Email matching check (relaxed - only warn, don't block)
        # The LinkedIn email might differ from registration email
        if linkedin_email and linkedin_email != user.email:
            logger.warning(
                f"LinkedIn email ({linkedin_email}) differs from user email ({user.email}) - "
                f"proceeding with verification anyway"
            )

        # All conditions met - auto-verify!
        try:
            from apps.profiles.services.linkedin_verification import (
                get_linkedin_verification_service,
            )

            service = get_linkedin_verification_service()
            is_verified, reasons = service.verify_linkedin_user(profile)

            if is_verified:
                logger.info(f"User {user.email} auto-verified as expert via LinkedIn")
                return True, "Verified via LinkedIn"
            else:
                logger.debug(f"User {user.email} not verified: {', '.join(reasons)}")
                return False, reasons[0] if reasons else "Verification failed"

        except Exception as e:
            logger.error(
                f"Error during LinkedIn verification for {user.email}: {str(e)}"
            )
            return False, f"Verification error: {str(e)}"

    def save_user(self, request, sociallogin, form=None):
        """
        Save NEW user from social login and extract profile data.

        NOTE: This method is ONLY called for NEW user signups via OAuth.
        For EXISTING users logging in, see pre_social_login().
        """
        # Ensure username is set before saving
        user = sociallogin.user
        if not user.username:
            email = user.email or sociallogin.account.extra_data.get("email", "")
            extra_data = sociallogin.account.extra_data

            # Get name from OAuth data
            name = extra_data.get("name", "")
            first_name = extra_data.get("given_name", "") or extra_data.get(
                "first_name", ""
            )
            last_name = extra_data.get("family_name", "") or extra_data.get(
                "last_name", ""
            )

            # Try to get the full name from various fields
            if not name and first_name:
                name = f"{first_name} {last_name}".strip() if last_name else first_name

            if name:
                username = self._clean_username_from_name(name)
                logger.info(
                    f"Using exact name '{name}' as username '{username}' for OAuth user {email}"
                )
            elif email:
                username = email.split("@")[0]
                logger.info(
                    f"Using email prefix '{username}' for OAuth user {email} (no name available)"
                )
            else:
                username = f"user_{uuid.uuid4().hex[:8]}"
                logger.info(f"Generated random username '{username}' for OAuth user")

            # Ensure uniqueness
            user.username = self._ensure_unique_username(username)

        user = super().save_user(request, sociallogin, form)

        # Always update profile data on every login (not just creation)
        profile, created = UserProfile.objects.get_or_create(user=user)

        # Extract provider-specific data
        provider = sociallogin.account.provider
        extra_data = sociallogin.account.extra_data

        logger.info(
            f"Processing OAuth data for provider: {provider} (new user: {created})"
        )
        logger.debug(f"Extra data keys: {list(extra_data.keys())}")

        if provider == "google":
            profile.oauth_provider = "google"
            if "picture" in extra_data:
                profile.profile_picture_url = extra_data["picture"]
            # Store Google ID
            if "sub" in extra_data:
                if hasattr(user, "google_id"):
                    user.google_id = extra_data["sub"]
                    user.save(update_fields=["google_id"])
            logger.info(f"Updated Google profile data for user {user.email}")

        elif provider in ["linkedin", "linkedin_oauth2", "openid_connect"]:
            logger.info(f"Processing LinkedIn OAuth data for NEW user {user.email}")

            # Update LinkedIn profile data
            self._update_linkedin_profile_data(profile, user, extra_data)

            # Save profile first before verification
            profile.save()

            # Trigger verification for taker role users
            linkedin_email = extra_data.get("email")
            is_verified, message = self._trigger_linkedin_verification(
                profile, user, linkedin_email
            )

            logger.info(
                f"LinkedIn verification result for {user.email}: "
                f"verified={is_verified}, message={message}"
            )

        # Always save profile data to database
        profile.save()

        if created:
            logger.info(f"Created profile for OAuth user {user.email} via {provider}")
        else:
            logger.info(
                f"Updated existing profile for OAuth user {user.email} via {provider}"
            )

        return user

    def pre_social_login(self, request, sociallogin):
        """
        Handle pre-login processing, account linking, and LinkedIn verification.

        CRITICAL: This method runs for EVERY OAuth login, including:
        1. NEW users (before save_user is called)
        2. EXISTING users (save_user is NOT called for existing users!)

        For EXISTING LinkedIn users, this is the ONLY place we can:
        - Update LinkedIn profile data
        - Trigger LinkedIn verification
        """
        provider = sociallogin.account.provider
        extra_data = sociallogin.account.extra_data
        email = extra_data.get("email", "unknown")

        logger.info(f"OAuth pre_social_login: provider={provider}, email={email}")

        # Try to connect to existing user with same email
        existing_user = None
        if email and email != "unknown":
            from apps.accounts.models import User

            try:
                existing_user = User.objects.get(email=email)
                if not sociallogin.is_existing:
                    sociallogin.connect(request, existing_user)
                    logger.info(f"Connected OAuth account to existing user {email}")
            except User.DoesNotExist:
                logger.debug(f"No existing user found for email {email}")

        # ========== EXISTING USER LINKEDIN VERIFICATION ==========
        # For EXISTING users logging in via LinkedIn, save_user() is NOT called.
        # We MUST handle LinkedIn data update and verification HERE.
        if existing_user and provider in [
            "linkedin",
            "linkedin_oauth2",
            "openid_connect",
        ]:
            logger.info(f"Processing LinkedIn login for EXISTING user {email}")

            # Get or create profile
            profile, _ = UserProfile.objects.get_or_create(user=existing_user)

            # Update LinkedIn profile data
            self._update_linkedin_profile_data(profile, existing_user, extra_data)

            logger.debug(
                f"Updated LinkedIn data for {email}: "
                f"linkedin_id={profile.linkedin_id}, "
                f"linkedin_email={profile.linkedin_email}"
            )

            # Save profile before verification
            profile.save()

            # Trigger verification for taker role users
            # This is the KEY FIX - existing users get verified here!
            linkedin_email = extra_data.get("email")
            is_verified, message = self._trigger_linkedin_verification(
                profile, existing_user, linkedin_email
            )

            logger.info(
                f"LinkedIn verification result for EXISTING user {email}: "
                f"verified={is_verified}, message={message}"
            )

        super().pre_social_login(request, sociallogin)
