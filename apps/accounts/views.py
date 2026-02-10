from allauth.account.models import EmailConfirmation, EmailConfirmationHMAC
from django.http import JsonResponse
from django.views.decorators.http import require_GET
from django.shortcuts import get_object_or_404

@require_GET
def verify_email_api(request, key):
    """
    Verify email using token.
    No redirect. No login. Just verification.
    """
    confirmation = None

    # Try HMAC-based confirmation (modern allauth)
    confirmation = EmailConfirmationHMAC.from_key(key)

    # Fallback for DB-based confirmation
    if confirmation is None:
        confirmation = get_object_or_404(EmailConfirmation, key=key)

    email_address = confirmation.email_address

    # Already verified → idempotent success
    if email_address.verified:
        return JsonResponse(
            {
                "success": True,
                "message": "Email already verified.",
            },
            status=200,
        )

    # Confirm (this does everything correctly)
    confirmation.confirm(request)

    # Activate user explicitly (important)
    user = email_address.user
    user.is_active = True
    user.save(update_fields=["is_active"])

    return JsonResponse(
        {
            "success": True,
            "message": "Email verified successfully.",
            "email": email_address.email,
        },
        status=200,
    )
