# apps/profiles/management/commands/verify_linkedin_experts.py
"""
Management command to verify LinkedIn-connected interviewers.

Usage:
    # Dry run (see who would be verified without making changes)
    python manage.py verify_linkedin_experts --dry-run

    # Actually verify eligible users
    python manage.py verify_linkedin_experts

    # Verbose output
    python manage.py verify_linkedin_experts --verbosity=2

This command scans all interviewers who:
1. Have connected via LinkedIn (oauth_provider='linkedin' or linkedin_id is set)
2. Are not yet verified
3. Meet verification criteria (experience, company match, etc.)
"""
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from apps.profiles.services.linkedin_verification import get_linkedin_verification_service


class Command(BaseCommand):
    help = 'Verify eligible interviewers based on LinkedIn data'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be verified without making changes'
        )
        parser.add_argument(
            '--min-experience',
            type=int,
            default=5,
            help='Minimum years of experience for auto-verification (default: 5)'
        )
    
    def handle(self, *args, **options):
        dry_run = options['dry_run']
        min_experience = options['min_experience']
        verbosity = options['verbosity']
        
        if dry_run:
            self.stdout.write(
                self.style.WARNING('=== DRY RUN MODE - No changes will be made ===')
            )
        
        self.stdout.write(
            f'\nSettings: min_experience={min_experience} years\n'
        )
        
        # Get verification service
        service = get_linkedin_verification_service()
        service.MIN_EXPERIENCE_YEARS = min_experience
        
        try:
            with transaction.atomic():
                results = service.batch_verify_interviewers(dry_run=dry_run)
                
                # Output results
                self.stdout.write(f'\n{"="*60}')
                self.stdout.write(f'VERIFICATION RESULTS')
                self.stdout.write(f'{"="*60}')
                self.stdout.write(f'Total interviewers checked: {results["checked"]}')
                self.stdout.write(f'Eligible for verification:  {results["eligible"]}')
                
                if not dry_run:
                    self.stdout.write(
                        self.style.SUCCESS(f'Successfully verified:      {results["verified"]}')
                    )
                
                # Show details if verbose
                if verbosity >= 2 and results['details']:
                    self.stdout.write(f'\n{"="*60}')
                    self.stdout.write('DETAILS:')
                    self.stdout.write(f'{"="*60}')
                    
                    for detail in results['details']:
                        status = '✓ VERIFIED' if detail['verified'] else '○ ELIGIBLE'
                        self.stdout.write(f'\n{status}: {detail["email"]}')
                        self.stdout.write(f'  Name: {detail["name"]}')
                        self.stdout.write(f'  Reasons:')
                        for reason in detail['reasons']:
                            self.stdout.write(f'    - {reason}')
                
                if dry_run and results['eligible'] > 0:
                    self.stdout.write(
                        self.style.WARNING(
                            f'\n→ Run without --dry-run to verify {results["eligible"]} user(s)'
                        )
                    )
                
                self.stdout.write(f'\n{"="*60}\n')
                
        except Exception as e:
            raise CommandError(f'Error during verification: {str(e)}')
