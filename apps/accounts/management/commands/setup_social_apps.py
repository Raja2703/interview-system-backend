from django.core.management.base import BaseCommand
from django.contrib.sites.models import Site
from allauth.socialaccount.models import SocialApp
from django.conf import settings
import environ

class Command(BaseCommand):
    help = 'Create SocialApp instances for Google and LinkedIn OAuth'

    def handle(self, *args, **options):
        env = environ.Env()
        environ.Env.read_env(settings.BASE_DIR / '.env')

        # Get the current site (localhost:8000)
        try:
            site = Site.objects.get(id=settings.SITE_ID)
        except Site.DoesNotExist:
            self.stdout.write(self.style.ERROR('Site not found. Creating default site...'))
            site = Site.objects.create(
                id=settings.SITE_ID,
                domain='127.0.0.1:8000',
                name='localhost'
            )

        # Create Google SocialApp
        google_client_id = env('GOOGLE_OAUTH_CLIENT_ID')
        google_client_secret = env('GOOGLE_OAUTH_CLIENT_SECRET')

        if google_client_id and google_client_secret:
            google_app, created = SocialApp.objects.get_or_create(
                provider='google',
                defaults={
                    'name': 'Google OAuth',
                    'client_id': google_client_id,
                    'secret': google_client_secret,
                }
            )
            if created:
                google_app.sites.add(site)
                self.stdout.write(self.style.SUCCESS('Created Google SocialApp'))
            else:
                # Update credentials if changed
                if google_app.client_id != google_client_id or google_app.secret != google_client_secret:
                    google_app.client_id = google_client_id
                    google_app.secret = google_client_secret
                    google_app.save()
                    self.stdout.write(self.style.SUCCESS('Updated Google SocialApp credentials'))
                if not google_app.sites.filter(id=site.id).exists():
                    google_app.sites.add(site)
                    self.stdout.write(self.style.SUCCESS('Added site to Google SocialApp'))
        else:
            self.stdout.write(self.style.WARNING('Google OAuth credentials not found in .env'))

        # Create LinkedIn SocialApp
        linkedin_client_id = env('LINKEDIN_OAUTH_CLIENT_ID')
        linkedin_client_secret = env('LINKEDIN_OAUTH_CLIENT_SECRET')

        if linkedin_client_id and linkedin_client_secret:
            linkedin_app, created = SocialApp.objects.get_or_create(
                provider='linkedin_oauth2',
                defaults={
                    'name': 'LinkedIn OAuth',
                    'client_id': linkedin_client_id,
                    'secret': linkedin_client_secret,
                }
            )
            if created:
                linkedin_app.sites.add(site)
                self.stdout.write(self.style.SUCCESS('Created LinkedIn SocialApp'))
            else:
                # Update credentials if changed
                if linkedin_app.client_id != linkedin_client_id or linkedin_app.secret != linkedin_client_secret:
                    linkedin_app.client_id = linkedin_client_id
                    linkedin_app.secret = linkedin_client_secret
                    linkedin_app.save()
                    self.stdout.write(self.style.SUCCESS('Updated LinkedIn SocialApp credentials'))
                if not linkedin_app.sites.filter(id=site.id).exists():
                    linkedin_app.sites.add(site)
                    self.stdout.write(self.style.SUCCESS('Added site to LinkedIn SocialApp'))
        else:
            self.stdout.write(self.style.WARNING('LinkedIn OAuth credentials not found in .env'))

        self.stdout.write(self.style.SUCCESS('SocialApp setup completed'))