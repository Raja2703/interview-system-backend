from django.urls import path, include
from django.http import JsonResponse
from . import api
from apps.accounts import api as accounts_api
from apps.common import api as common_api

def api_root(request):
    """API root endpoint with available endpoints and user status."""
    response_data = {
        "name": "Interview Platform API",
        "version": "1.0",
        "authenticated": request.user.is_authenticated,
        "documentation": {
            "swagger": "/swagger/",
            "redoc": "/redoc/"
        }
    }
    
    # Add user info if authenticated
    if request.user.is_authenticated:
        from apps.profiles.models import UserProfile
        
        try:
            profile = UserProfile.objects.get(user=request.user)
            response_data["user"] = {
                "username": request.user.username,
                "email": request.user.email,
                "roles": profile.get_role_names(),
                "is_verified": profile.is_verified_user,
                "needs_role_selection": not profile.has_any_role()
            }
        except UserProfile.DoesNotExist:
            response_data["user"] = {
                "username": request.user.username,
                "email": request.user.email,
                "needs_role_selection": True
            }
    
    # Add available endpoints
    response_data["endpoints"] = {
        "auth": {
            "status": "/api/auth-status/",
            "login": "/accounts/login/",
            "signup": "/accounts/signup/",
            "logout": "/accounts/logout/",
            "google": "/api/auth/google/login/",
            "linkedin": "/api/auth/linkedin/login/",
            "token_refresh": "/api/token/refresh/"
        },
        "user": {
            "profile": "/api/profile/",
            "profile_update": "/api/profile/update/",
            "select_role": "/api/select-role/",
            "add_role": "/api/add-role/",
            "user_detail": "/api/users/{uuid}/",
        },
        "interviews": {
            "list_create": "/api/interviews/requests/",
            "detail": "/api/interviews/requests/{uuid}/",
            "accept": "/api/interviews/requests/{uuid}/accept/",
            "reject": "/api/interviews/requests/{uuid}/reject/",
            "cancel": "/api/interviews/requests/{uuid}/cancel/",
            "complete": "/api/interviews/requests/{uuid}/complete/",
            "not_attended": "/api/interviews/requests/{uuid}/not-attended/",
            "join": "/api/interviews/{uuid}/join/",
            "dashboard": "/api/interviews/dashboard/",
        },
        "notifications": {
            "list": "/api/notifications/",
            "detail": "/api/notifications/{id}/",
            "unread_count": "/api/notifications/unread-count/",
            "mark_read": "/api/notifications/{id}/mark-read/",
            "mark_all_read": "/api/notifications/mark-all-read/",
            "websocket": "ws://host/ws/notifications/",
        },
        "profiles": {
            "attenders": "/api/profiles/attenders/",
            "takers": "/api/profiles/takers/",
            "both": "/api/profiles/both/",
        },
        "enums": "/api/enums/",
        "admin": {
            "users_list": "/api/admin/users/",
            "user_detail": "/api/admin/users/{uuid}/",
            "verification_detail": "/api/admin/users/{uuid}/verification/",
            "interviews_list": "/api/admin/interviews/",
            "interview_detail": "/api/admin/interviews/{uuid}/",
            "interview_action": "/api/admin/interviews/{uuid}/action/",
        },
        "dashboard": "/dashboard/"
    }
    
    return JsonResponse(response_data)


urlpatterns = [
    # API root
    path('', api_root, name='api_root'),
    
    # ========== ENUM API (NO AUTH REQUIRED) ==========
    path('enums/', common_api.enums_api, name='enums'),
    
    # Profile and role management
    path('profile/', api.ProfileAPI.as_view(), name='profile'),
    path('profile/update/', api.ProfileUpdateAPI.as_view(), name='profile_update'),
    path('select-role/', api.select_role_view, name='select_role'),
    path('add-role/', api.add_role_view, name='add_role'),
    
    # ========== USER DETAIL API (UUID-based) ==========
    path('users/<uuid:user_id>/', api.UserDetailAPI.as_view(), name='user_detail'),
    
    # ========== PROFILE LISTING APIs ==========
    path('profiles/attenders/', api.AttendersListAPI.as_view(), name='profiles_attenders'),
    path('profiles/takers/', api.TakersListAPI.as_view(), name='profiles_takers'),
    path('profiles/both/', api.BothRolesListAPI.as_view(), name='profiles_both'),
    
    # ========== ONBOARDING APIs ==========
    path('onboarding/status/', api.onboarding_status_view, name='onboarding_status'),
    path('onboarding/step/', api.onboarding_step_view, name='onboarding_step'),
    path('onboarding/complete/', api.onboarding_complete_view, name='onboarding_complete'),
    
    # ========== ADMIN APIs (UUID-based) ==========
    path('admin/users/', api.AdminUserListAPI.as_view(), name='admin_user_list'),
    path('admin/users/<uuid:user_id>/', api.AdminUserDetailAPI.as_view(), name='admin_user_detail'),
    
    # ========== ADMIN VERIFICATION APIs ==========
    # NOTE: Manual verify/unverify endpoints REMOVED
    # Verification is now automatic via LinkedIn OAuth for taker role users
    # Only read-only verification detail is available
    path('admin/users/<uuid:user_id>/verification/', api.AdminUserVerificationDetailAPI.as_view(), name='admin_user_verification'),
    
    # Authentication
    path('auth-status/', accounts_api.auth_status, name='auth_status'),
    path('token/refresh/', accounts_api.DecoratedTokenRefreshView.as_view(), name='token_refresh_api'),
    path('oauth-complete/', accounts_api.oauth_complete, name='oauth_complete'),
    path('auth-endpoints/', accounts_api.auth_endpoints, name='auth_endpoints'),
]
