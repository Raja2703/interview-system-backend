# apps/interviews/permissions.py
"""
Permission classes for interview-related views.
Updated to support multi-role users and interview-specific permissions.
"""

from rest_framework.permissions import BasePermission


class IsAttender(BasePermission):
    """
    Permission class to check if user has 'attender' role.
    Works with multi-role users - user only needs to have 'attender' as one of their roles.
    """
    message = "You must have the Interview Attender role to access this resource."
    
    def has_permission(self, request, view):
        if not hasattr(request.user, 'profile'):
            return False
        # UPDATED: Use has_role() for multi-role support
        return request.user.profile.has_role('attender')


class IsTaker(BasePermission):
    """
    Permission class to check if user has 'taker' role.
    Works with multi-role users - user only needs to have 'taker' as one of their roles.
    """
    message = "You must have the Interview Taker role to access this resource."
    
    def has_permission(self, request, view):
        if not hasattr(request.user, 'profile'):
            return False
        # UPDATED: Use has_role() for multi-role support
        return request.user.profile.has_role('taker')


class HasAnyRole(BasePermission):
    """
    Permission class to check if user has at least one role assigned.
    Useful for endpoints that require role selection but don't care which role.
    """
    message = "You must have at least one role assigned to access this resource."
    
    def has_permission(self, request, view):
        if not hasattr(request.user, 'profile'):
            return False
        return request.user.profile.has_any_role()


class HasBothRoles(BasePermission):
    """
    Permission class to check if user has both 'attender' and 'taker' roles.
    Useful for admin-like features that require full access.
    """
    message = "You must have both Interview Attender and Interview Taker roles to access this resource."
    
    def has_permission(self, request, view):
        if not hasattr(request.user, 'profile'):
            return False
        return request.user.profile.is_both()


class IsAttenderOrTaker(BasePermission):
    """
    Permission class to check if user has either 'attender' or 'taker' role.
    This is essentially the same as HasAnyRole for this system's current roles.
    """
    message = "You must have either Interview Attender or Interview Taker role to access this resource."
    
    def has_permission(self, request, view):
        if not hasattr(request.user, 'profile'):
            return False
        profile = request.user.profile
        return profile.has_role('attender') or profile.has_role('taker')


class OnboardingCompleted(BasePermission):
    """
    Permission class to check if user has completed all required onboarding steps.
    This ensures that users cannot access protected resources until onboarding is complete.
    
    Works with multi-role users - validates onboarding for all assigned roles.
    """
    message = "You must complete your profile onboarding before accessing this resource."
    
    def has_permission(self, request, view):
        if not hasattr(request.user, 'profile'):
            return False
        
        profile = request.user.profile
        
        # User must have at least one role selected
        if not profile.has_any_role():
            return False
        
        # Check if onboarding is complete (data-driven validation)
        return not profile.is_onboarding_required()


class IsOnboardedAttender(BasePermission):
    """
    Permission class to check if user has 'attender' role AND has completed onboarding.
    Combines role check with onboarding completion check.
    """
    message = "You must be an Interview Attender with completed onboarding to access this resource."
    
    def has_permission(self, request, view):
        if not hasattr(request.user, 'profile'):
            return False
        
        profile = request.user.profile
        
        if not profile.has_role('attender'):
            return False
        
        return not profile.is_onboarding_required()


class IsOnboardedTaker(BasePermission):
    """
    Permission class to check if user has 'taker' role AND has completed onboarding.
    Combines role check with onboarding completion check.
    """
    message = "You must be an Interview Taker with completed onboarding to access this resource."
    
    def has_permission(self, request, view):
        if not hasattr(request.user, 'profile'):
            return False
        
        profile = request.user.profile
        
        if not profile.has_role('taker'):
            return False
        
        return not profile.is_onboarding_required()


# ========== ADMIN PERMISSION CLASSES ==========


class IsAdmin(BasePermission):
    """
    Permission class to check if user is a platform admin.
    Admin is identified via is_staff or is_superuser.
    
    Admins have full access and bypass:
    - Role selection requirements
    - Onboarding completion requirements
    """
    message = "You must be an admin to access this resource."
    
    def has_permission(self, request, view):
        return bool(
            request.user and 
            request.user.is_authenticated and 
            (request.user.is_staff or request.user.is_superuser)
        )


class IsAdminOrReadOnly(BasePermission):
    """
    Permission class that allows:
    - Read access (GET, HEAD, OPTIONS) to any authenticated user
    - Write access (POST, PUT, PATCH, DELETE) only to admins
    """
    message = "You must be an admin to modify this resource."
    
    SAFE_METHODS = ('GET', 'HEAD', 'OPTIONS')
    
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        
        if request.method in self.SAFE_METHODS:
            return True
        
        return request.user.is_staff or request.user.is_superuser


class IsAdminOrSelf(BasePermission):
    """
    Permission class that allows:
    - Admins to access any user's data
    - Regular users to access only their own data
    
    Useful for user detail/edit endpoints.
    """
    message = "You can only access your own data or be an admin."
    
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated)
    
    def has_object_permission(self, request, view, obj):
        # Admin can access anything
        if request.user.is_staff or request.user.is_superuser:
            return True
        
        # Check if accessing own data
        # obj could be User, UserProfile, or related model
        if hasattr(obj, 'user'):
            return obj.user == request.user
        
        return obj == request.user


# ========== INTERVIEW-SPECIFIC PERMISSIONS ==========


class IsInterviewParticipant(BasePermission):
    """
    Permission class to check if user is a participant in the interview.
    Used for viewing interview details and joining rooms.
    """
    message = "You are not a participant in this interview."
    
    def has_object_permission(self, request, view, obj):
        # obj is InterviewRequest
        return request.user in [obj.sender, obj.receiver]


class IsInterviewSender(BasePermission):
    """
    Permission class to check if user is the sender of the interview request.
    Used for cancelling interview requests.
    """
    message = "Only the sender of this interview request can perform this action."
    
    def has_object_permission(self, request, view, obj):
        return request.user == obj.sender


class IsInterviewReceiver(BasePermission):
    """
    Permission class to check if user is the receiver of the interview request.
    Used for accepting/rejecting interview requests.
    """
    message = "Only the receiver of this interview request can perform this action."
    
    def has_object_permission(self, request, view, obj):
        return request.user == obj.receiver


class CanJoinInterview(BasePermission):
    """
    Permission class to check if user can join the interview.
    
    Requirements:
    - User is a participant (sender or receiver)
    - Interview is accepted
    - Interview is within joinable time window
    - User is NOT an admin (admins cannot join LiveKit rooms)
    """
    message = "You cannot join this interview."
    
    def has_permission(self, request, view):
        # Admins cannot join LiveKit rooms
        if request.user.is_staff or request.user.is_superuser:
            self.message = "Admins cannot join interview rooms."
            return False
        return True
    
    def has_object_permission(self, request, view, obj):
        # Check participant
        if request.user not in [obj.sender, obj.receiver]:
            self.message = "You are not a participant in this interview."
            return False
        
        # Check status
        if obj.status != 'accepted':
            self.message = f"Interview is not accepted (status: {obj.status})."
            return False
        
        # Check time window
        if not obj.is_joinable():
            time_status = obj.get_time_window_status()
            if time_status == 'too_early':
                self.message = "Interview room is not open yet. Please come back closer to the scheduled time."
            elif time_status == 'too_late':
                self.message = "Interview time window has expired."
            else:
                self.message = "Interview cannot be joined at this time."
            return False
        
        return True


class CanAcceptRejectInterview(BasePermission):
    """
    Permission class for accepting or rejecting interview requests.
    
    Requirements:
    - User is the receiver (interviewer/taker)
    - Interview is in pending status
    """
    message = "You cannot accept or reject this interview request."
    
    def has_object_permission(self, request, view, obj):
        # Must be receiver
        if request.user != obj.receiver:
            self.message = "Only the interviewer can accept or reject this request."
            return False
        
        # Must be pending
        if obj.status != 'pending':
            self.message = f"Interview request is not pending (status: {obj.status})."
            return False
        
        return True


class CanCancelInterview(BasePermission):
    """
    Permission class for cancelling interview requests.
    
    Requirements:
    - User is the sender (attender) OR admin
    - Interview is pending or accepted
    """
    message = "You cannot cancel this interview request."
    
    def has_object_permission(self, request, view, obj):
        is_admin = request.user.is_staff or request.user.is_superuser
        
        # Admin can cancel any interview
        if is_admin:
            if obj.status not in ['pending', 'accepted']:
                self.message = f"Cannot cancel interview with status '{obj.status}'."
                return False
            return True
        
        # Sender can cancel
        if request.user != obj.sender:
            self.message = "Only the sender can cancel this interview request."
            return False
        
        # Must be pending or accepted
        if obj.status not in ['pending', 'accepted']:
            self.message = f"Cannot cancel interview with status '{obj.status}'."
            return False
        
        return True
