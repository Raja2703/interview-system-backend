# apps/accounts/signals.py
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.conf import settings
from apps.profiles.models import UserProfile

User = settings.AUTH_USER_MODEL

@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    """
    Create UserProfile only on user creation.
    Use get_or_create to handle race conditions.
    """
    if created:
        UserProfile.objects.get_or_create(user=instance)

        from django.dispatch import receiver
from allauth.account.signals import email_confirmed
from django.contrib.auth import get_user_model

User = get_user_model()

@receiver(email_confirmed)
def activate_user_on_email_confirm(request, email_address, **kwargs):
    user = email_address.user

    
    user.is_active = True
    user.save(update_fields=["is_active"])
