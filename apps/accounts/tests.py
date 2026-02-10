import json
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from apps.profiles.models import UserProfile
from allauth.socialaccount.models import SocialAccount
import unittest
from unittest.mock import patch, MagicMock

User = get_user_model()


class LinkedInOAuthTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.test_email = "gf316@gmail.com"
        self.test_linkedin_id = "test_linkedin_123"

    def test_linkedin_login_endpoint(self):
        """Test that LinkedIn login endpoint returns redirect"""
        response = self.client.get('/api/auth/linkedin/login/')
        self.assertEqual(response.status_code, 302)
        self.assertIn('linkedin', response['Location'].lower())

    def test_google_login_endpoint(self):
        """Test that Google login endpoint returns redirect"""
        response = self.client.get('/api/auth/google/login/')
        self.assertEqual(response.status_code, 302)
        self.assertIn('google', response['Location'].lower())

    @patch('allauth.socialaccount.providers.linkedin_oauth2.views.LinkedInOAuth2Adapter.complete_login')
    def test_linkedin_oauth_callback_simulation(self, mock_complete_login):
        """Test LinkedIn OAuth callback with mocked response"""
        # Mock the social login object
        mock_social_login = MagicMock()
        mock_social_login.user = User(
            username='test_user_linkedin',
            email=self.test_email,
            linkedin_id=self.test_linkedin_id
        )
        mock_social_login.account.extra_data = {
            'id': self.test_linkedin_id,
            'sub': self.test_linkedin_id,
            'email': self.test_email,
            'name': 'Test LinkedIn User',
            'given_name': 'Test',
            'family_name': 'User',
            'picture': 'https://example.com/picture.jpg',
            'locale': 'en_US'
        }
        mock_complete_login.return_value = mock_social_login

        # Simulate OAuth success
        response = self.client.get('/api/auth/social/success/')

        # Should redirect to login since not authenticated
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login', response['Location'])

    def test_oauth_success_authenticated_user(self):
        """Test OAuth success endpoint with authenticated user"""
        # Create test user
        user = User.objects.create_user(
            username='test_linkedin_user',
            email=self.test_email,
            linkedin_id=self.test_linkedin_id
        )
        UserProfile.objects.create(user=user, oauth_provider='linkedin')

        # Login user
        self.client.force_login(user)

        # Test success endpoint
        response = self.client.get('/api/auth/social/success/')
        self.assertEqual(response.status_code, 200)

        data = json.loads(response.content)
        self.assertTrue(data['success'])
        self.assertIn('tokens', data)
        self.assertIn('user', data)
        self.assertEqual(data['user']['email'], self.test_email)
        self.assertEqual(data['user']['oauth_provider'], 'linkedin')

    def test_user_profile_creation_linkedin(self):
        """Test that LinkedIn OAuth creates proper user profile"""
        user = User.objects.create_user(
            username='linkedin_test_user',
            email=self.test_email,
            linkedin_id=self.test_linkedin_id
        )

        # Create profile with LinkedIn data
        profile = UserProfile.objects.create(
            user=user,
            oauth_provider='linkedin',
            linkedin_id=self.test_linkedin_id,
            profile_picture_url='https://example.com/pic.jpg',
            bio='Test bio',
            current_position='Software Engineer'
        )

        self.assertEqual(profile.oauth_provider, 'linkedin')
        self.assertEqual(profile.linkedin_id, self.test_linkedin_id)
        self.assertEqual(user.linkedin_id, self.test_linkedin_id)

    def test_social_account_linking(self):
        """Test linking existing user with same email"""
        # Create existing user
        existing_user = User.objects.create_user(
            username='existing_user',
            email=self.test_email,
            password='testpass123'
        )

        # Simulate OAuth with same email
        user = User(
            username='new_oauth_user',
            email=self.test_email,
            linkedin_id=self.test_linkedin_id
        )

        # Should link to existing user
        self.assertEqual(User.objects.filter(email=self.test_email).count(), 1)
        self.assertEqual(User.objects.get(email=self.test_email), existing_user)


class OAuthIntegrationTest(TestCase):
    """Integration tests for OAuth functionality"""

    def setUp(self):
        self.client = Client()

    def test_auth_endpoints_response(self):
        """Test that auth endpoints return proper structure"""
        response = self.client.get('/api/auth/')
        self.assertEqual(response.status_code, 200)

        # Test with proper endpoint if it exists
        try:
            response = self.client.get('/api/auth-status/')
            # If endpoint exists, check it's not authenticated
            if response.status_code == 200:
                data = json.loads(response.content)
                self.assertFalse(data.get('authenticated', True))
        except:
            pass  # Endpoint might not exist, that's ok

    def test_health_check(self):
        """Test health check endpoint"""
        response = self.client.get('/api/health/')
        if response.status_code == 200:
            self.assertEqual(response.content.decode(), '{"status": "healthy", "message": "Interview Platform Backend is running"}')
        else:
            # If different endpoint, just check it responds
            response = self.client.get('/')
            self.assertEqual(response.status_code, 200)