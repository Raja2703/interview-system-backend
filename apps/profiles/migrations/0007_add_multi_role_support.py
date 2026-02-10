# apps/profiles/migrations/0002_add_multi_role_support.py
"""
Migration to add multi-role support via ManyToMany relationship.

This migration:
1. Adds the 'roles' ManyToMany field to UserProfile
2. Creates default Role records (attender, taker)
3. Migrates existing single-role data to multi-role format
4. Does NOT remove deprecated fields (kept for rollback safety)

Run with: python manage.py migrate profiles
"""

from django.db import migrations, models


def create_default_roles(apps, schema_editor):
    """Create the default attender and taker roles if they don't exist."""
    Role = apps.get_model('profiles', 'Role')
    
    Role.objects.get_or_create(
        name='attender',
        defaults={
            'description': 'Can attend interviews and send interview requests.',
            'is_active': True,
            'permissions': {}
        }
    )
    
    Role.objects.get_or_create(
        name='taker',
        defaults={
            'description': 'Can conduct interviews and receive interview requests.',
            'is_active': True,
            'permissions': {}
        }
    )


def migrate_single_role_to_multi_role(apps, schema_editor):
    """
    Migrate existing single-role data to multi-role format.
    
    This handles:
    - profile.role (CharField) -> roles ManyToMany
    - profile.new_role (FK) -> roles ManyToMany
    """
    UserProfile = apps.get_model('profiles', 'UserProfile')
    Role = apps.get_model('profiles', 'Role')
    
    for profile in UserProfile.objects.all():
        roles_to_add = set()
        
        # Check deprecated CharField role
        if profile.role:
            roles_to_add.add(profile.role)
        
        # Check deprecated FK new_role
        if profile.new_role_id:
            try:
                fk_role = Role.objects.get(id=profile.new_role_id)
                roles_to_add.add(fk_role.name)
            except Role.DoesNotExist:
                pass
        
        # Add roles to the new ManyToMany field
        for role_name in roles_to_add:
            try:
                role = Role.objects.get(name=role_name)
                profile.roles.add(role)
            except Role.DoesNotExist:
                # Create the role if it doesn't exist
                if role_name in ['attender', 'taker']:
                    role = Role.objects.create(
                        name=role_name,
                        description=f'{role_name.title()} role (auto-created during migration)',
                        is_active=True
                    )
                    profile.roles.add(role)


def reverse_migrate_roles(apps, schema_editor):
    """
    Reverse migration: Copy first role from ManyToMany back to CharField.
    """
    UserProfile = apps.get_model('profiles', 'UserProfile')
    
    for profile in UserProfile.objects.all():
        first_role = profile.roles.first()
        if first_role:
            profile.role = first_role.name
            profile.save(update_fields=['role'])


class Migration(migrations.Migration):

    dependencies = [
        ('profiles', '0006_userprofile_onboarding_completed'),
    ]

    operations = [
        # Step 1: Update Role model fields
        migrations.AlterModelOptions(
            name='role',
            options={'ordering': ['name']},
        ),
        migrations.AlterField(
            model_name='role',
            name='description',
            field=models.TextField(blank=True, default=''),
        ),
        migrations.AlterField(
            model_name='role',
            name='permissions',
            field=models.JSONField(blank=True, default=dict),
        ),
        
        # Step 2: Add the roles ManyToMany field
        migrations.AddField(
            model_name='userprofile',
            name='roles',
            field=models.ManyToManyField(
                blank=True,
                help_text='User can have multiple roles (attender, taker, or both)',
                related_name='profiles',
                to='profiles.role'
            ),
        ),
        
        # Step 3: Update related_name for deprecated new_role field
        migrations.AlterField(
            model_name='userprofile',
            name='new_role',
            field=models.ForeignKey(
                blank=True,
                help_text='DEPRECATED: Use roles ManyToMany field instead',
                null=True,
                on_delete=models.deletion.SET_NULL,
                related_name='user_profiles_deprecated',
                to='profiles.role'
            ),
        ),
        
        # Step 4: Update help_text for deprecated role CharField
        migrations.AlterField(
            model_name='userprofile',
            name='role',
            field=models.CharField(
                blank=True,
                choices=[('attender', 'Interview Attender'), ('taker', 'Interview Taker')],
                help_text='DEPRECATED: Use roles ManyToMany field instead',
                max_length=20,
                null=True
            ),
        ),
        
        # Step 5: Run data migrations
        migrations.RunPython(
            create_default_roles,
            reverse_code=migrations.RunPython.noop
        ),
        migrations.RunPython(
            migrate_single_role_to_multi_role,
            reverse_code=reverse_migrate_roles
        ),
    ]
