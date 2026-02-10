# apps/profiles/services/linkedin_verification.py
"""
LinkedIn Verified Expert System.

SIMPLIFIED Verification Logic:
- Interviewers (taker role) who login via LinkedIn are AUTOMATICALLY verified
- NO complex criteria required (removed experience, company, email domain checks)

Rules:
- Email signup users are NOT verified by default
- LinkedIn OAuth users with TAKER role are auto-verified
- Attenders are NEVER auto-verified (verification is for interviewers only)
- Email verification (django-allauth) is SEPARATE from LinkedIn verification

IMPORTANT DISTINCTION:
- Email verification = django-allauth email confirmation for signup users
- LinkedIn verification = expert verification for interviewers (taker role)
- These are TWO DIFFERENT concepts - DO NOT MIX THEM
"""
import logging
from django.utils import timezone

logger = logging.getLogger(__name__)


class LinkedInVerificationService:
    """
    Simplified service for auto-verifying interviewers via LinkedIn.
    
    Verification is automatic for any user who:
    1. Has LinkedIn OAuth connection (oauth_provider='linkedin' OR linkedin_id exists)
    2. Has the 'taker' (interviewer) role
    """
    
    def __init__(self):
        self.verification_reasons = []
    
    def verify_linkedin_user(self, user_profile, linkedin_data=None):
        """
        Auto-verify a taker user who logged in via LinkedIn.
        
        Args:
            user_profile: UserProfile instance
            linkedin_data: Optional dict with LinkedIn OAuth data (for future use)
        
        Returns:
            tuple: (is_verified: bool, reasons: list)
        """
        self.verification_reasons = []
        
        # Skip if already verified
        if user_profile.is_verified_user:
            return True, ['Already verified as expert']
        
        # Must have LinkedIn connection
        has_linkedin = (
            user_profile.oauth_provider == 'linkedin' or 
            bool(user_profile.linkedin_id)
        )
        
        if not has_linkedin:
            self.verification_reasons.append('Not connected via LinkedIn')
            return False, self.verification_reasons
        
        # Must have taker (interviewer) role - only interviewers can be verified
        if not user_profile.is_taker():
            self.verification_reasons.append('Not an interviewer (taker role required)')
            return False, self.verification_reasons
        
        # All conditions met - auto-verify!
        user_profile.verify_user(
            verified_via='linkedin',
            notes='Automatically verified via LinkedIn OAuth login'
        )
        
        self.verification_reasons.append('LinkedIn OAuth verification successful')
        
        logger.info(
            f"User {user_profile.user.email} auto-verified as expert via LinkedIn"
        )
        
        return True, self.verification_reasons
    
    def batch_verify_interviewers(self, dry_run=False):
        """
        Batch verify eligible interviewers who have LinkedIn connection.
        
        This is called by the management command.
        
        Args:
            dry_run: If True, don't actually update, just report
        
        Returns:
            dict: {
                'checked': int,
                'eligible': int,
                'verified': int,
                'details': list
            }
        """
        from apps.profiles.models import UserProfile
        
        results = {
            'checked': 0,
            'eligible': 0,
            'verified': 0,
            'details': []
        }
        
        # Get all interviewers with LinkedIn connection who are not verified
        profiles = UserProfile.objects.filter(
            roles__name='taker',
            is_verified_user=False
        ).filter(
            # Has LinkedIn connection
            oauth_provider='linkedin'
        ) | UserProfile.objects.filter(
            roles__name='taker',
            is_verified_user=False,
            linkedin_id__isnull=False
        )
        
        profiles = profiles.distinct()
        
        for profile in profiles:
            results['checked'] += 1
            
            # Check if eligible (has LinkedIn + taker role)
            has_linkedin = (
                profile.oauth_provider == 'linkedin' or 
                bool(profile.linkedin_id)
            )
            is_taker = profile.is_taker()
            
            if has_linkedin and is_taker:
                results['eligible'] += 1
                
                if not dry_run:
                    profile.verify_user(
                        verified_via='linkedin',
                        notes='Batch verified via LinkedIn connection'
                    )
                    results['verified'] += 1
                
                results['details'].append({
                    'email': profile.user.email,
                    'name': profile.linkedin_full_name or profile.name,
                    'reasons': ['LinkedIn + Taker role'],
                    'verified': not dry_run
                })
        
        return results


# Singleton instance
linkedin_verification_service = LinkedInVerificationService()


def get_linkedin_verification_service():
    """Get the LinkedIn verification service instance."""
    return linkedin_verification_service
