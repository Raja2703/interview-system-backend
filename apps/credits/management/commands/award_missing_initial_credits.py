from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from apps.profiles.models import UserProfile, Role
from apps.credits.services import CreditService
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Award initial credits to existing users who are attenders but did not receive the signup bonus.'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help='Show who would be credited without making changes')

    def handle(self, *args, **options):
        dry_run = options.get('dry_run')
        User = get_user_model()

        profiles = UserProfile.objects.filter(roles__name=Role.ATTENDER, roles__is_active=True).select_related('user')
        total = 0
        awarded = 0
        skipped = 0

        for profile in profiles.distinct():
            total += 1
            user = profile.user
            try:
                balance = getattr(user, 'credit_balance', None)
                has_received = False
                if balance is not None:
                    has_received = bool(balance.has_received_initial_credits)

                if has_received:
                    skipped += 1
                    self.stdout.write(f"SKIP {user.email}: already received initial credits")
                    continue

                self.stdout.write(f"AWARD {user.email}: awarding initial credits")
                if not dry_run:
                    success, message, txn = CreditService.award_initial_credits(user)
                    if success:
                        awarded += 1
                        self.stdout.write(f"  -> success: {message}")
                    else:
                        skipped += 1
                        self.stdout.write(f"  -> skipped: {message}")

            except Exception as e:
                logger.exception(f"Failed to award credits for {user.email}: {e}")
                self.stderr.write(f"ERROR {user.email}: {e}")

        self.stdout.write("")
        self.stdout.write(f"Profiles scanned: {total}")
        self.stdout.write(f"Awarded: {awarded}")
        self.stdout.write(f"Skipped: {skipped}")