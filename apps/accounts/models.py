# apps/accounts/models.py
from django.contrib.auth.models import AbstractUser
from django.db import models

class User(AbstractUser):
    """
    Authentication model.
    - Email is primary identifier
    - Username is required for signup
    - Password OR OAuth
    """

    email = models.EmailField(unique=True)
    
    # Username is required and unique
    username = models.CharField(max_length=150, unique=True)

    # Optional OAuth identifiers
    google_id = models.CharField(max_length=255, blank=True, null=True)
    linkedin_id = models.CharField(max_length=255, blank=True, null=True)

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username']  # Username required when creating superuser

    def __str__(self):
        return self.email
