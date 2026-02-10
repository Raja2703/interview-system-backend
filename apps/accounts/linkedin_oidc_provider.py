#apps\accounts\linkedin_oidc_provider.py
from allauth.socialaccount.providers.linkedin_oauth2.provider import LinkedInOAuth2Provider
from allauth.socialaccount.providers.linkedin_oauth2.views import LinkedInOAuth2Adapter
from allauth.socialaccount.providers.oauth2.views import OAuth2LoginView, OAuth2CallbackView
import jwt
import logging

logger = logging.getLogger(__name__)

class CustomLinkedInOAuth2Adapter(LinkedInOAuth2Adapter):
    """Custom adapter that extracts user info from ID token and forces re-authentication"""
    
    def get_auth_params(self, request, action):
        """Override to add parameters that force LinkedIn to show login screen"""
        params = super().get_auth_params(request, action)
        
        # Force LinkedIn to always show the login screen and account selection
        params.update({
            'prompt': 'login',  # Force login screen
            'approval_prompt': 'force',  # Force approval screen
        })
        
        logger.info(f"LinkedIn OAuth auth params: {params}")
        return params
    
    def complete_login(self, request, app, token, response, **kwargs):
        """Override to extract user info from ID token"""
        try:
            # The response dict contains the id_token
            id_token = response.get('id_token')
            
            if id_token:
                # Decode the JWT without verification (we trust LinkedIn's token)
                decoded = jwt.decode(id_token, options={"verify_signature": False})
                logger.info(f"Decoded ID token: {decoded}")
                
                # Create extra_data from the decoded token
                extra_data = {
                    'id': decoded.get('sub'),
                    'sub': decoded.get('sub'),
                    'email': decoded.get('email'),
                    'email_verified': decoded.get('email_verified'),
                    'name': decoded.get('name'),
                    'given_name': decoded.get('given_name'),
                    'family_name': decoded.get('family_name'),
                    'picture': decoded.get('picture'),
                    'locale': decoded.get('locale'),
                }
                
                # Call parent's complete_login with our extracted data
                from allauth.socialaccount.models import SocialLogin
                login = self.get_provider().sociallogin_from_response(request, extra_data)
                
                return login
            else:
                logger.error("No id_token in response")
                raise ValueError("No id_token in response")
                
        except Exception as e:
            logger.error(f"Error in complete_login: {e}")
            import traceback
            logger.error(traceback.format_exc())
            raise

class CustomLinkedInOAuth2LoginView(OAuth2LoginView):
    """Custom login view that ensures fresh authentication"""
    
    def dispatch(self, request, *args, **kwargs):
        """Override to ensure session is clean before OAuth"""
        # Clear any existing LinkedIn-related session data
        linkedin_session_keys = [key for key in request.session.keys() if 'linkedin' in key.lower() or 'oauth' in key.lower()]
        for key in linkedin_session_keys:
            del request.session[key]
        
        logger.info("Cleared LinkedIn session data before OAuth initiation")
        return super().dispatch(request, *args, **kwargs)

oauth2_login = CustomLinkedInOAuth2LoginView.adapter_view(CustomLinkedInOAuth2Adapter)
oauth2_callback = OAuth2CallbackView.adapter_view(CustomLinkedInOAuth2Adapter)