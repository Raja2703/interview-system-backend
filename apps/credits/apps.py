# apps/credits/apps.py
from django.apps import AppConfig


class CreditsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.credits'
    verbose_name = 'Credits System'

    def ready(self):
        """Import signals when app is ready."""
        import apps.credits.signals  # noqa: F401
