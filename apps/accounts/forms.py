# apps/accounts/forms.py
from allauth.account.forms import SignupForm, ResetPasswordForm
from django import forms
from django.contrib.auth import get_user_model
from allauth.account.adapter import get_adapter
from allauth.account.utils import filter_users_by_email
from django.conf import settings
from django.contrib.auth.tokens import default_token_generator
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

User = get_user_model()


class CustomSignupForm(SignupForm):
    """Custom signup form that requires username."""

    username = forms.CharField(
        max_length=150,
        required=True,
        widget=forms.TextInput(
            attrs={"placeholder": "Enter your username", "class": "form-control"}
        ),
        help_text="Required. 150 characters or fewer. Letters, digits and @/./+/-/_ only.",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Make username field required
        self.fields["username"].required = True
        # Reorder fields to show username first
        field_order = ["username", "email", "password"]
        self.order_fields(field_order)

    def clean_username(self):
        """Validate username uniqueness."""
        username = self.cleaned_data.get("username")
        if username and User.objects.filter(username=username).exists():
            raise forms.ValidationError("A user with that username already exists.")
        return username

    def save(self, request):
        """Save the user with the provided username."""
        user = super().save(request)
        user.username = self.cleaned_data["username"]
        user.save()
        return user


class FrontendResetPasswordForm(ResetPasswordForm):
    def save(self, request, **kwargs):
        """
        Override save to force the usage of FRONTEND_URL
        """
        email = self.cleaned_data["email"]
        users = filter_users_by_email(email)

        if not users:
            return email

        adapter = get_adapter(request)
        frontend_url = getattr(
            settings, "FRONTEND_URL", "http://localhost:3000"
        ).rstrip("/")

        for user in users:
            # 1. Generate the link manually
            uid = urlsafe_base64_encode(force_bytes(user.pk))
            token = default_token_generator.make_token(user)
            password_reset_url = (
                f"{frontend_url}/reset-password?uid={uid}&token={token}"
            )

            # 2. Create the context expected by the email template
            context = {
                "user": user,
                "password_reset_url": password_reset_url,
                "request": request,
            }

            # 3. Send the mail using the adapter, but passing our custom context
            # Note: This template name is the default allauth template
            adapter.send_mail("account/email/password_reset_key", email, context)

        return email
