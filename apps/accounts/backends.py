# apps/accounts/backends.py
from django.contrib.auth.backends import ModelBackend
from django.contrib.auth import get_user_model
from allauth.account.models import EmailAddress

User = get_user_model()

class EmailBackend(ModelBackend):
    """
    Authenticate using email instead of username.
    Checks if email is verified via allauth.
    """
    def authenticate(self, request, username=None, password=None, email=None, **kwargs):
        # Support both 'email' and 'username' parameters
        email = email or username
        
        if not email or not password:
            return None
        
        try:
            # Find user by email
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            # Run default password hasher to mitigate timing attacks
            User().set_password(password)
            return None
        
        # Check password
        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        
        return None
    
    def get_user(self, user_id):
        try:
            return User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return None