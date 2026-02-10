from django.core.management.base import BaseCommand
from django.test import Client
from django.contrib.auth import get_user_model
from apps.profiles.models import UserProfile
import json

User = get_user_model()

class Command(BaseCommand):
    help = 'Test OAuth endpoints'

    def handle(self, *args, **options):
        client = Client()

        self.stdout.write("Testing OAuth endpoints...")
        self.stdout.write("=" * 50)

        # Test LinkedIn login endpoint
        self.stdout.write("\n1. Testing LinkedIn login endpoint...")
        try:
            response = client.get('/api/auth/linkedin/login/')
            self.stdout.write(f"   Status: {response.status_code}")
            if response.status_code == 302:
                location = response['Location']
                self.stdout.write(f"   Redirect to: {location}")
                if 'linkedin' in location.lower():
                    self.stdout.write(self.style.SUCCESS("   ✅ Correctly redirects to LinkedIn"))
                else:
                    self.stdout.write(self.style.ERROR("   ❌ Redirect doesn't contain 'linkedin'"))
            else:
                self.stdout.write(self.style.ERROR(f"   ❌ Expected 302, got {response.status_code}"))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"   ❌ Error: {e}"))

        # Test Google login endpoint
        self.stdout.write("\n2. Testing Google login endpoint...")
        try:
            response = client.get('/api/auth/google/login/')
            self.stdout.write(f"   Status: {response.status_code}")
            if response.status_code == 302:
                location = response['Location']
                self.stdout.write(f"   Redirect to: {location}")
                if 'google' in location.lower():
                    self.stdout.write(self.style.SUCCESS("   ✅ Correctly redirects to Google"))
                else:
                    self.stdout.write(self.style.ERROR("   ❌ Redirect doesn't contain 'google'"))
            else:
                self.stdout.write(self.style.ERROR(f"   ❌ Expected 302, got {response.status_code}"))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"   ❌ Error: {e}"))

        # Test OAuth success endpoint (should redirect when not authenticated)
        self.stdout.write("\n3. Testing OAuth success endpoint (not authenticated)...")
        try:
            response = client.get('/api/auth/social/success/')
            self.stdout.write(f"   Status: {response.status_code}")
            if response.status_code == 302:
                self.stdout.write(self.style.SUCCESS("   ✅ Correctly redirects when not authenticated"))
            else:
                self.stdout.write(self.style.ERROR(f"   ❌ Expected 302, got {response.status_code}"))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"   ❌ Error: {e}"))

        # Test with authenticated user
        self.stdout.write("\n4. Testing OAuth success endpoint (authenticated)...")
        try:
            # Create or get test user
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
                self.stdout.write(f"   Created test user: {test_user.email}")

            # Force login
            client.force_login(test_user)

            response = client.get('/api/auth/social/success/')
            self.stdout.write(f"   Status: {response.status_code}")

            if response.status_code == 200:
                try:
                    data = json.loads(response.content)
                    self.stdout.write("   Response data:")
                    self.stdout.write(f"     Success: {data.get('success')}")
                    self.stdout.write(f"     Has tokens: {'tokens' in data}")
                    self.stdout.write(f"     Has user data: {'user' in data}")

                    if 'user' in data:
                        user_data = data['user']
                        self.stdout.write(f"     User email: {user_data.get('email')}")
                        self.stdout.write(f"     OAuth provider: {user_data.get('oauth_provider')}")

                        if user_data.get('email') == "gf316@gmail.com":
                            self.stdout.write(self.style.SUCCESS("   ✅ Correct user email returned"))
                        else:
                            self.stdout.write(self.style.ERROR("   ❌ Wrong user email"))

                        if user_data.get('oauth_provider') == 'linkedin':
                            self.stdout.write(self.style.SUCCESS("   ✅ Correct OAuth provider"))
                        else:
                            self.stdout.write(self.style.ERROR("   ❌ Wrong OAuth provider"))

                except json.JSONDecodeError:
                    self.stdout.write(self.style.ERROR("   ❌ Invalid JSON response"))
                    self.stdout.write(f"   Raw content: {response.content[:200]}")
            else:
                self.stdout.write(self.style.ERROR(f"   ❌ Expected 200, got {response.status_code}"))

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"   ❌ Error: {e}"))
            import traceback
            self.stderr.write(traceback.format_exc())

        # Test user data
        self.stdout.write("\n5. Checking user data...")
        try:
            user = User.objects.filter(email="gf316@gmail.com").first()
            if user:
                self.stdout.write(f"   User exists: {user.email}")
                self.stdout.write(f"   Username: {user.username}")
                self.stdout.write(f"   LinkedIn ID: {user.linkedin_id}")

                profile = UserProfile.objects.filter(user=user).first()
                if profile:
                    self.stdout.write(f"   Profile OAuth provider: {profile.oauth_provider}")
                    self.stdout.write(f"   Profile LinkedIn ID: {profile.linkedin_id}")
                    self.stdout.write(self.style.SUCCESS("   ✅ User profile complete"))
                else:
                    self.stdout.write(self.style.ERROR("   ❌ No user profile found"))
            else:
                self.stdout.write(self.style.ERROR("   ❌ No user found with email gf316@gmail.com"))

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"   ❌ Error checking user: {e}"))

        self.stdout.write("\n" + "=" * 50)
        self.stdout.write("OAuth test completed!")