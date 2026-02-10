#!/usr/bin/env python
"""
Simple script to test OAuth endpoints without Django test framework
"""
import os
import sys
import django
from pathlib import Path

# Add project directory to Python path
BASE_DIR = Path(__file__).resolve().parent
sys.path.append(str(BASE_DIR))

# Configure Django settings
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.test import Client
from django.contrib.auth import get_user_model
from apps.profiles.models import UserProfile
import json

User = get_user_model()

def test_oauth_endpoints():
    """Test OAuth endpoints"""
    client = Client()

    print("Testing OAuth endpoints...")

    # Test LinkedIn login endpoint
    print("\n1. Testing LinkedIn login endpoint...")
    try:
        response = client.get('/api/auth/linkedin/login/')
        print(f"   Status: {response.status_code}")
        if response.status_code == 302:
            location = response['Location']
            print(f"   Redirect to: {location}")
            if 'linkedin' in location.lower():
                print("   ✅ Correctly redirects to LinkedIn")
            else:
                print("   ❌ Redirect doesn't contain 'linkedin'")
        else:
            print(f"   ❌ Expected 302, got {response.status_code}")
    except Exception as e:
        print(f"   ❌ Error: {e}")

    # Test Google login endpoint
    print("\n2. Testing Google login endpoint...")
    try:
        response = client.get('/api/auth/google/login/')
        print(f"   Status: {response.status_code}")
        if response.status_code == 302:
            location = response['Location']
            print(f"   Redirect to: {location}")
            if 'google' in location.lower():
                print("   ✅ Correctly redirects to Google")
            else:
                print("   ❌ Redirect doesn't contain 'google'")
        else:
            print(f"   ❌ Expected 302, got {response.status_code}")
    except Exception as e:
        print(f"   ❌ Error: {e}")

    # Test OAuth success endpoint (should redirect when not authenticated)
    print("\n3. Testing OAuth success endpoint (not authenticated)...")
    try:
        response = client.get('/api/auth/social/success/')
        print(f"   Status: {response.status_code}")
        if response.status_code == 302:
            print("   ✅ Correctly redirects when not authenticated")
        else:
            print(f"   ❌ Expected 302, got {response.status_code}")
    except Exception as e:
        print(f"   ❌ Error: {e}")

    # Test with mock authenticated user
    print("\n4. Testing OAuth success endpoint (authenticated)...")
    try:
        # Create test user
        test_user, created = User.objects.get_or_create(
            email="gf316@gmail.com",
            defaults={
                'username': 'test_linkedin_user',
                'linkedin_id': 'test_linkedin_123'
            }
        )

        if created:
            UserProfile.objects.get_or_create(
                user=test_user,
                defaults={'oauth_provider': 'linkedin'}
            )

        # Force login
        client.force_login(test_user)

        response = client.get('/api/auth/social/success/')
        print(f"   Status: {response.status_code}")

        if response.status_code == 200:
            try:
                data = json.loads(response.content)
                print(f"   Response: {json.dumps(data, indent=2)}")

                # Check expected fields
                if 'success' in data and data['success']:
                    print("   ✅ Success response")
                else:
                    print("   ❌ Missing success field")

                if 'tokens' in data:
                    print("   ✅ Contains JWT tokens")
                else:
                    print("   ❌ Missing tokens")

                if 'user' in data:
                    user_data = data['user']
                    print(f"   User email: {user_data.get('email')}")
                    print(f"   OAuth provider: {user_data.get('oauth_provider')}")
                    if user_data.get('email') == "gf316@gmail.com":
                        print("   ✅ Correct user email")
                    else:
                        print("   ❌ Wrong user email")
                else:
                    print("   ❌ Missing user data")

            except json.JSONDecodeError:
                print("   ❌ Invalid JSON response")
                print(f"   Raw content: {response.content[:200]}")
        else:
            print(f"   ❌ Expected 200, got {response.status_code}")

    except Exception as e:
        print(f"   ❌ Error: {e}")
        import traceback
        traceback.print_exc()

def test_user_creation():
    """Test user creation with LinkedIn data"""
    print("\n5. Testing user creation with LinkedIn data...")

    try:
        # Check if test user exists
        user = User.objects.filter(email="gf316@gmail.com").first()
        if user:
            print(f"   Found existing user: {user.email}")
            print(f"   Username: {user.username}")
            print(f"   LinkedIn ID: {user.linkedin_id}")

            profile = UserProfile.objects.filter(user=user).first()
            if profile:
                print(f"   Profile OAuth provider: {profile.oauth_provider}")
                print(f"   Profile LinkedIn ID: {profile.linkedin_id}")
                print("   ✅ User profile exists with LinkedIn data")
            else:
                print("   ❌ No user profile found")
        else:
            print("   No user found with email gf316@gmail.com")

    except Exception as e:
        print(f"   ❌ Error: {e}")

if __name__ == '__main__':
    print("OAuth Test Script")
    print("=" * 50)

    test_oauth_endpoints()
    test_user_creation()

    print("\n" + "=" * 50)
    print("Test completed!")