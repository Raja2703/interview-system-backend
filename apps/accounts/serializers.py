#apps\accounts\serializers.py
from rest_framework import serializers

class LoginRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)

class SignupRequestSerializer(serializers.Serializer):
    username = serializers.CharField()
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)

class TokenSerializer(serializers.Serializer):
    access = serializers.CharField()
    refresh = serializers.CharField()

class UserPayloadSerializer(serializers.Serializer):
    """
    Serializer for user payload in API responses.
    Updated to support multi-role users.
    """
    username = serializers.CharField()
    email = serializers.EmailField()
    uuid = serializers.UUIDField(required=False, allow_null=True)
    # NEW: List of roles for multi-role support
    roles = serializers.ListField(
        child=serializers.CharField(),
        allow_empty=True,
        help_text='List of user roles (e.g., ["attender", "taker"])'
    )
    # DEPRECATED: Single role for backward compatibility
    role = serializers.CharField(allow_null=True)
    oauth_provider = serializers.CharField(allow_null=True)
    has_role = serializers.BooleanField()
    profile_complete = serializers.BooleanField()

class AuthResponseSerializer(serializers.Serializer):
    success = serializers.BooleanField()
    tokens = TokenSerializer()
    user = UserPayloadSerializer()
    next_step = serializers.CharField()

class LogoutResponseSerializer(serializers.Serializer):
    success = serializers.BooleanField()
    message = serializers.CharField()

class AuthStatusResponseSerializer(serializers.Serializer):
    authenticated = serializers.BooleanField()
    user = UserPayloadSerializer(required=False)
    tokens = TokenSerializer(required=False)
    next_step = serializers.CharField(required=False)
    message = serializers.CharField(required=False)
