import logging
from django.http import JsonResponse
from allauth.socialaccount.providers.linkedin_oauth2.views import LinkedInOAuth2Adapter
from allauth.socialaccount.providers.oauth2.client import OAuth2Client
import requests

logger = logging.getLogger(__name__)

def test_linkedin_token_exchange(request):
    """Manually test LinkedIn token exchange"""
    code = request.GET.get('code')
    state = request.GET.get('state')
    
    if not code:
        return JsonResponse({'error': 'No code provided'})
    
    # Get LinkedIn app credentials
    from allauth.socialaccount.models import SocialApp
    from django.contrib.sites.shortcuts import get_current_site
    
    try:
        site = get_current_site(request)
        app = SocialApp.objects.get(provider='linkedin_oauth2', sites=site)
        
        # Manually try to exchange code for token
        token_url = 'https://www.linkedin.com/oauth/v2/accessToken'
        callback_url = request.build_absolute_uri('/accounts/linkedin_oauth2/login/callback/')
        
        data = {
            'grant_type': 'authorization_code',
            'code': code,
            'redirect_uri': callback_url,
            'client_id': app.client_id,
            'client_secret': app.secret,
        }
        
        logger.info(f"Attempting token exchange with callback URL: {callback_url}")
        
        response = requests.post(token_url, data=data)
        
        return JsonResponse({
            'status': 'Token exchange attempt',
            'response_status': response.status_code,
            'response_body': response.json() if response.headers.get('content-type') == 'application/json' else response.text,
            'callback_url_used': callback_url,
            'client_id': app.client_id,
        }, json_dumps_params={'indent': 2})
        
    except Exception as e:
        logger.error(f"Error in token exchange test: {e}", exc_info=True)
        return JsonResponse({
            'error': str(e),
            'error_type': type(e).__name__,
        })